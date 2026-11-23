"""The one strict check of a Codex `--json` event stream, used by every real call and by the decoy test.

A turn is harmless only if it is made of known events whose items are plain answers (`agent_message`,
`reasoning`) and every item that started also completed. Any tool item (command, file change, web search,
MCP call), any item or event kind not listed here, and a turn that never completed is refused. The safe side
is "not verified", so a new Codex that reports things differently is stopped rather than trusted.

MCP: Codex 0.170 has three built-in MCP resource tools (`list_mcp_resources`, `list_mcp_resource_templates`,
`read_mcp_resource`) that no setting turns off (openai/codex#6049; checked on 0.170 with `mcp_servers={}` and
the feature flags). `--ignore-user-config` leaves no MCP server, so they cannot reach data, but nothing here
can prove which server answered, so every `mcp_tool_call` is refused and the decoy prompt never asks for MCP.
"""
from collections import Counter

EVENTS = frozenset({'thread.started', 'turn.started', 'turn.completed', 'item.started', 'item.updated',
                    'item.completed'})
ITEMS = frozenset({'agent_message', 'reasoning'})
TOOL_ITEMS = frozenset({'command_execution', 'file_change', 'web_search', 'mcp_tool_call'})


MCP_REASON = 'tool_event:mcp_tool_call'


def only_mcp(kinds):
    """Whether an event-kind count (the second value of `codex_events`) holds nothing but plain answers and
    `mcp_tool_call` items: no other tool, no unknown item or event."""
    for kind in kinds:
        event, _, item = kind.partition('/')
        if event not in EVENTS or (item and item not in ITEMS and item != 'mcp_tool_call'):
            return False
    return True


def is_tool_reason(reason):
    """A reason that means a tool, or something that may be one, showed up (never retryable, never transient)."""
    return bool(reason) and (reason.startswith('tool_event:') or reason == 'unknown_item')


def codex_events(events):
    """(first reason the stream is not a harmless turn or None, count of event kinds). Tool reasons win."""
    kinds, tool, structure, open_items = Counter(), None, None, set()
    for event in events:
        kind = event.get('type')
        item = event.get('item')
        kinds[f'{kind}/{item.get("type")}' if isinstance(item, dict) else str(kind)] += 1
        if kind not in EVENTS:
            structure = structure or 'unknown_event'
        if isinstance(kind, str) and kind.startswith('item.'):
            if not isinstance(item, dict):
                tool = tool or 'unknown_item'
                continue
            item_kind = item.get('type')
            if item_kind in TOOL_ITEMS:
                tool = tool or 'tool_event:' + item_kind
            elif item_kind not in ITEMS:
                tool = tool or 'unknown_item'
            item_id = item.get('id')
            if kind == 'item.started':
                if item_id is None:
                    structure = structure or 'incomplete_item'
                else:
                    open_items.add(item_id)
            elif kind == 'item.completed':
                open_items.discard(item_id)
    if open_items:
        structure = structure or 'incomplete_item'
    if not kinds['turn.completed']:
        structure = structure or 'no_turn_completed'
    return tool or structure, dict(kinds)
