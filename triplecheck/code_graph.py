"""Tree-sitter based dependency graph for Go and Python."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from triplecheck.state import FileContent

# Lazy imports for optional dependencies
_ts = None
_ts_python = None
_ts_go = None
_nx = None


def _ensure_deps():
    """Lazy-import tree-sitter and networkx; raise ImportError if missing."""
    global _ts, _ts_python, _ts_go, _nx
    if _ts is not None:
        return
    try:
        import tree_sitter as ts
        import tree_sitter_python as ts_python
        import tree_sitter_go as ts_go
        import networkx as nx
        _ts = ts
        _ts_python = ts_python
        _ts_go = ts_go
        _nx = nx
    except ImportError as e:
        raise ImportError(
            f"Tree-sitter dependencies not installed. "
            f"Install with: pip install -e '.[graph]'\n"
            f"Missing: {e}"
        ) from e


@dataclass
class CodeSymbol:
    name: str
    kind: str  # function | class | type | method
    file: str
    start_line: int
    end_line: int


@dataclass
class CodeEdge:
    caller: str  # "file:symbol" or "file" for top-level
    callee: str  # "file:symbol" or module name
    kind: str  # call | import


@dataclass
class CodeGraph:
    symbols: list[CodeSymbol] = field(default_factory=list)
    edges: list[CodeEdge] = field(default_factory=list)

    def get_subgraph(self, symbol_name: str, depth: int = 2) -> CodeGraph:
        """Extract a subgraph centered on a symbol, up to `depth` hops."""
        _ensure_deps()
        G = _nx.DiGraph()
        for edge in self.edges:
            G.add_edge(edge.caller, edge.callee, kind=edge.kind)

        # BFS from the symbol node
        related = set()
        queue = deque([(symbol_name, 0)])
        visited = set()
        while queue:
            node, d = queue.popleft()
            if node in visited or d > depth:
                continue
            visited.add(node)
            related.add(node)
            if G.has_node(node):
                for neighbor in list(G.successors(node)) + list(G.predecessors(node)):
                    queue.append((neighbor, d + 1))

        sub_symbols = [s for s in self.symbols if f"{s.file}:{s.name}" in related]
        sub_edges = [
            e for e in self.edges
            if e.caller in related or e.callee in related
        ]
        return CodeGraph(symbols=sub_symbols, edges=sub_edges)


def _get_python_parser():
    """Create a tree-sitter parser for Python."""
    _ensure_deps()
    lang = _ts.Language(_ts_python.language())
    return _ts.Parser(lang)


def _get_go_parser():
    """Create a tree-sitter parser for Go."""
    _ensure_deps()
    lang = _ts.Language(_ts_go.language())
    return _ts.Parser(lang)


def _node_text(node, source: bytes) -> str:
    """Extract text from a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _parse_python(tree, source: bytes, filepath: str) -> tuple[list[CodeSymbol], list[CodeEdge]]:
    """Extract symbols and edges from a Python AST."""
    symbols = []
    edges = []
    root = tree.root_node

    def visit(node, scope=""):
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _node_text(name_node, source)
                full_name = f"{scope}.{name}" if scope else name
                symbols.append(CodeSymbol(
                    name=full_name,
                    kind="function",
                    file=filepath,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                ))
                # Recurse into function body with scope
                for child in node.children:
                    visit(child, full_name)
                return

        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _node_text(name_node, source)
                full_name = f"{scope}.{name}" if scope else name
                symbols.append(CodeSymbol(
                    name=full_name,
                    kind="class",
                    file=filepath,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                ))
                for child in node.children:
                    visit(child, full_name)
                return

        elif node.type == "import_statement":
            text = _node_text(node, source)
            # import foo.bar → module "foo.bar"
            parts = text.replace("import ", "").strip().split(",")
            for part in parts:
                mod = part.strip().split(" as ")[0].strip()
                if mod:
                    edges.append(CodeEdge(
                        caller=filepath,
                        callee=mod,
                        kind="import",
                    ))

        elif node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            if module_node:
                mod = _node_text(module_node, source)
                edges.append(CodeEdge(
                    caller=filepath,
                    callee=mod,
                    kind="import",
                ))

        elif node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node:
                callee = _node_text(func_node, source)
                caller = f"{filepath}:{scope}" if scope else filepath
                edges.append(CodeEdge(
                    caller=caller,
                    callee=callee,
                    kind="call",
                ))

        for child in node.children:
            visit(child, scope)

    visit(root)
    return symbols, edges


def _parse_go(tree, source: bytes, filepath: str) -> tuple[list[CodeSymbol], list[CodeEdge]]:
    """Extract symbols and edges from a Go AST."""
    symbols = []
    edges = []
    root = tree.root_node

    def visit(node, scope=""):
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _node_text(name_node, source)
                symbols.append(CodeSymbol(
                    name=name,
                    kind="function",
                    file=filepath,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                ))
                for child in node.children:
                    visit(child, name)
                return

        elif node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            receiver = node.child_by_field_name("receiver")
            if name_node:
                name = _node_text(name_node, source)
                recv_type = ""
                if receiver:
                    # Extract receiver type name
                    for child in receiver.named_children:
                        type_node = child.child_by_field_name("type")
                        if type_node:
                            recv_type = _node_text(type_node, source).lstrip("*")
                full_name = f"{recv_type}.{name}" if recv_type else name
                symbols.append(CodeSymbol(
                    name=full_name,
                    kind="method",
                    file=filepath,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                ))
                for child in node.children:
                    visit(child, full_name)
                return

        elif node.type == "type_declaration":
            for spec in node.named_children:
                if spec.type == "type_spec":
                    name_node = spec.child_by_field_name("name")
                    if name_node:
                        name = _node_text(name_node, source)
                        kind = "type"
                        type_node = spec.child_by_field_name("type")
                        if type_node and type_node.type in ("struct_type", "interface_type"):
                            kind = type_node.type.replace("_type", "")
                        symbols.append(CodeSymbol(
                            name=name,
                            kind=kind,
                            file=filepath,
                            start_line=spec.start_point[0] + 1,
                            end_line=spec.end_point[0] + 1,
                        ))

        elif node.type == "import_declaration":
            for child in node.named_children:
                if child.type == "import_spec":
                    path_node = child.child_by_field_name("path")
                    if path_node:
                        path = _node_text(path_node, source).strip('"')
                        edges.append(CodeEdge(
                            caller=filepath,
                            callee=path,
                            kind="import",
                        ))
                elif child.type == "import_spec_list":
                    for spec in child.named_children:
                        if spec.type == "import_spec":
                            path_node = spec.child_by_field_name("path")
                            if path_node:
                                path = _node_text(path_node, source).strip('"')
                                edges.append(CodeEdge(
                                    caller=filepath,
                                    callee=path,
                                    kind="import",
                                ))

        elif node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            if func_node:
                callee = _node_text(func_node, source)
                caller = f"{filepath}:{scope}" if scope else filepath
                edges.append(CodeEdge(
                    caller=caller,
                    callee=callee,
                    kind="call",
                ))

        for child in node.children:
            visit(child, scope)

    visit(root)
    return symbols, edges


def build_graph(files: list[FileContent], target: Path) -> CodeGraph:
    """Build a code graph from files using tree-sitter.

    Only parses Python and Go files. Other languages are skipped.
    """
    _ensure_deps()
    all_symbols = []
    all_edges = []

    python_parser = None
    go_parser = None

    for f in files:
        filepath = str(f.path)
        source = f.content.encode("utf-8")

        if f.language == "python":
            if python_parser is None:
                python_parser = _get_python_parser()
            tree = python_parser.parse(source)
            symbols, edges = _parse_python(tree, source, filepath)
            all_symbols.extend(symbols)
            all_edges.extend(edges)

        elif f.language == "go":
            if go_parser is None:
                go_parser = _get_go_parser()
            tree = go_parser.parse(source)
            symbols, edges = _parse_go(tree, source, filepath)
            all_symbols.extend(symbols)
            all_edges.extend(edges)

    return CodeGraph(symbols=all_symbols, edges=all_edges)


def smart_batch(
    files: list[FileContent],
    target: Path,
    max_lines: int = 6000,
    max_files: int = 5,
) -> list[list[FileContent]]:
    """Batch files by dependency subgraph instead of just line count.

    Files that are closely related (call each other, share imports)
    are grouped together so the LLM sees related code in the same batch.
    Falls back to simple line-count batching if graph building fails.
    """
    _ensure_deps()

    graph = build_graph(files, target)

    # Build a networkx graph of file-level dependencies
    G = _nx.Graph()
    file_set = {str(f.path) for f in files}
    for f in files:
        G.add_node(str(f.path))

    for edge in graph.edges:
        # Extract file from caller/callee
        caller_file = edge.caller.split(":")[0]
        callee_file = edge.callee.split(":")[0]
        if caller_file in file_set and callee_file in file_set and caller_file != callee_file:
            G.add_edge(caller_file, callee_file)

    # Get connected components
    components = list(_nx.connected_components(G))

    # Map files to their component
    file_to_component: dict[str, int] = {}
    for i, component in enumerate(components):
        for f in component:
            file_to_component[f] = i

    # Sort components by total line count (biggest first)
    component_files: dict[int, list[FileContent]] = {}
    for f in files:
        comp_id = file_to_component.get(str(f.path), -1)
        component_files.setdefault(comp_id, []).append(f)

    # Pre-compute line counts for all components
    component_lines: dict[int, int] = {}
    for comp_id, comp_files in component_files.items():
        component_lines[comp_id] = sum(f.content.count("\n") + 1 for f in comp_files)

    # Pack components into batches respecting max_lines
    batches: list[list[FileContent]] = []
    current_batch: list[FileContent] = []
    current_lines = 0

    for comp_id in sorted(component_files.keys(),
                          key=lambda c: component_lines[c],
                          reverse=True):
        comp_files = component_files[comp_id]
        comp_lines = component_lines[comp_id]

        if comp_lines > max_lines or len(comp_files) > max_files:
            # Component too large — split it
            if current_batch:
                batches.append(current_batch)
                current_batch = []
                current_lines = 0
            # Add files from this component one by one
            for f in comp_files:
                f_lines = f.content.count("\n") + 1
                if (current_lines + f_lines > max_lines or len(current_batch) >= max_files) and current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_lines = 0
                current_batch.append(f)
                current_lines += f_lines
        elif current_lines + comp_lines > max_lines or len(current_batch) + len(comp_files) > max_files:
            if current_batch:
                batches.append(current_batch)
            current_batch = list(comp_files)
            current_lines = comp_lines
        else:
            current_batch.extend(comp_files)
            current_lines += comp_lines

    if current_batch:
        batches.append(current_batch)

    return batches
