from app.models.workflow import Workflow
from app.models.validation import ValidationIssue, ValidationResult, Severity
from app.catalog import get_catalog_entry, TRIGGER_TYPES


def validate_structural(workflow: Workflow) -> list[ValidationIssue]:
    issues = []
    ids = [n.id for n in workflow.nodes]

    if len(ids) != len(set(ids)):
        issues.append(ValidationIssue(severity=Severity.BLOCKING, code="DUPLICATE_NODE_ID", message="Duplicate node IDs found"))

    if not workflow.nodes:
        issues.append(ValidationIssue(severity=Severity.BLOCKING, code="EMPTY_WORKFLOW", message="Workflow must contain at least one node"))

    node_id_set = set(ids)
    for edge in workflow.edges:
        if edge.from_ not in node_id_set:
            issues.append(ValidationIssue(node_id=edge.from_, severity=Severity.BLOCKING, code="EDGE_UNKNOWN_SOURCE", message=f"Edge references unknown source node '{edge.from_}'"))
        if edge.to not in node_id_set:
            issues.append(ValidationIssue(node_id=edge.to, severity=Severity.BLOCKING, code="EDGE_UNKNOWN_TARGET", message=f"Edge references unknown target node '{edge.to}'"))

    return issues


def validate_semantic(workflow: Workflow) -> list[ValidationIssue]:
    issues = []
    for node in workflow.nodes:
        entry = get_catalog_entry(node.type.value)
        if entry is None:
            issues.append(ValidationIssue(node_id=node.id, severity=Severity.BLOCKING, code="UNKNOWN_NODE_TYPE", message=f"Node type '{node.type}' is not in the catalog"))
            continue

        for field_name, field_spec in entry.config_schema.items():
            value = node.config.get(field_name)
            if field_spec.required and (value is None or value == ""):
                issues.append(ValidationIssue(node_id=node.id, severity=Severity.BLOCKING, code="MISSING_CONFIG_FIELD", field=field_name, message=f"{node.type.value} requires '{field_name}'"))
            elif value is not None and field_spec.pattern and not field_spec.matches(value):
                issues.append(ValidationIssue(node_id=node.id, severity=Severity.WARNING, code="INVALID_CONFIG_FORMAT", field=field_name, message=f"{field_name} value '{value}' does not match expected format"))
    return issues


def validate_graph_rules(workflow: Workflow) -> list[ValidationIssue]:
    issues = []
    incoming = {e.to for e in workflow.edges}
    outgoing = {e.from_ for e in workflow.edges}

    for node in workflow.nodes:
        if node.type.value in TRIGGER_TYPES and node.id in incoming:
            issues.append(ValidationIssue(node_id=node.id, severity=Severity.BLOCKING, code="TRIGGER_HAS_INCOMING_EDGE", message=f"Trigger node '{node.id}' cannot have incoming connections"))

    if len(workflow.nodes) > 1:
        connected = incoming | outgoing
        for node in workflow.nodes:
            if node.id not in connected:
                issues.append(ValidationIssue(node_id=node.id, severity=Severity.WARNING, code="ORPHAN_NODE", message=f"Node '{node.id}' is not connected to the workflow"))

    if _has_cycle(workflow):
        issues.append(ValidationIssue(severity=Severity.BLOCKING, code="CYCLE_DETECTED", message="Workflow graph contains a cycle"))

    if not any(n.type.value in TRIGGER_TYPES for n in workflow.nodes):
        issues.append(ValidationIssue(severity=Severity.WARNING, code="NO_TRIGGER_NODE", message="Workflow has no trigger node and will never run automatically"))

    return issues


def _has_cycle(workflow: Workflow) -> bool:
    adj: dict[str, list[str]] = {n.id: [] for n in workflow.nodes}
    for e in workflow.edges:
        adj.setdefault(e.from_, []).append(e.to)

    visited, in_stack = set(), set()

    def dfs(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        for neighbor in adj.get(node, []):
            if neighbor in in_stack:
                return True
            if neighbor not in visited and dfs(neighbor):
                return True
        in_stack.discard(node)
        return False

    return any(dfs(n) for n in adj if n not in visited)


def validate_workflow(workflow: Workflow) -> ValidationResult:
    issues: list[ValidationIssue] = []

    structural = validate_structural(workflow)
    issues.extend(structural)
    if any(i.severity == Severity.BLOCKING for i in structural):
        return ValidationResult(valid=False, issues=issues)

    issues.extend(validate_semantic(workflow))
    issues.extend(validate_graph_rules(workflow))

    return ValidationResult(valid=not any(i.severity == Severity.BLOCKING for i in issues), issues=issues)