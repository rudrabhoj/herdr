use super::*;
use crate::api::schema::{Method, PaneDirection, SplitDirection};
use crate::input::KeybindAction;

use super::super::control::{control_action_for_key, control_sticky_action};

/// Three workspaces; ws_1 has three tabs and two agent panes in its first tab.
fn control_snapshot() -> ClientShellSnapshot {
    let mut snapshot = snapshot();
    for (index, workspace_id) in ["ws_2", "ws_3"].into_iter().enumerate() {
        let mut workspace = snapshot.workspaces[0].clone();
        workspace.workspace_id = workspace_id.into();
        workspace.active_tab_id = format!("tab_{workspace_id}");
        workspace.number = index + 2;
        workspace.label = workspace_id.into();
        workspace.focused = false;
        snapshot.workspaces.push(workspace);
        let mut tab = snapshot.tabs[0].clone();
        tab.tab_id = format!("tab_{workspace_id}");
        tab.workspace_id = workspace_id.into();
        tab.focused = false;
        snapshot.tabs.push(tab);
    }
    for tab_id in ["tab_2", "tab_3"] {
        let mut tab = snapshot.tabs[0].clone();
        tab.tab_id = tab_id.into();
        tab.focused = false;
        snapshot.tabs.insert(1, tab);
    }
    snapshot.tabs[1..3].sort_by(|a, b| a.tab_id.cmp(&b.tab_id));
    let mut second_pane = snapshot.panes[0].clone();
    second_pane.pane_id = "pane_2".into();
    second_pane.focused = false;
    snapshot.panes.push(second_pane);
    snapshot.agents = ["pane_1", "pane_2"]
        .into_iter()
        .map(|pane_id| crate::protocol::ClientShellAgent {
            pane_id: pane_id.into(),
            workspace_id: "ws_1".into(),
            tab_id: "tab_1".into(),
            name: Some(pane_id.into()),
            display_agent: None,
            agent: Some("pi".into()),
            title: None,
            terminal_title: None,
            terminal_title_stripped: None,
            agent_status: AgentStatus::Idle,
            state_change_seq: 0,
            state_labels: Vec::new(),
            tokens: Vec::new(),
            focused: pane_id == "pane_1",
        })
        .collect();
    snapshot
}

fn state_with(config: &Config, snapshot: ClientShellSnapshot) -> ClientShellState {
    let mut state = ClientShellState::new(ClientShellConfig::from_config(config));
    state.set_snapshot(Box::new(snapshot));
    state.set_pane_surface(surface());
    state
}

fn control_state(scope: ControlScope) -> ClientShellState {
    let mut state = state_with(&Config::default(), control_snapshot());
    state.mode = ClientShellMode::Control(scope);
    state
}

fn endpoint_methods(outcome: &ClientShellInput) -> Vec<&Method> {
    outcome
        .actions
        .iter()
        .filter_map(|action| match action {
            ClientShellAction::Endpoint { request, .. } => Some(&request.method),
            _ => None,
        })
        .collect()
}

fn key(code: KeyCode) -> crate::input::TerminalKey {
    crate::input::TerminalKey::new(code, KeyModifiers::empty())
}

#[test]
fn entry_bindings_open_each_scope_and_esc_or_enter_leave() {
    let mut state = state_with(&Config::default(), control_snapshot());
    for (rhs, scope) in [
        (&b"t"[..], ControlScope::Tabs),
        (&b"S"[..], ControlScope::Spaces),
        (&b"a"[..], ControlScope::Agents),
        (&b"f"[..], ControlScope::Panes),
    ] {
        state.handle_input_bytes(&[0x02]);
        let outcome = state.handle_input_bytes(rhs);
        assert!(
            outcome.requests.is_empty(),
            "entry key must not reach the pane"
        );
        assert_eq!(state.mode, ClientShellMode::Control(scope));
        state.handle_input_bytes(b"\x1b");
        assert_eq!(state.mode, ClientShellMode::Terminal);
    }

    state.mode = ClientShellMode::Control(ControlScope::Tabs);
    state.handle_input_bytes(b"\r");
    assert_eq!(state.mode, ClientShellMode::Terminal);
}

#[test]
fn shared_verbs_dispatch_per_scope() {
    use KeybindAction::*;
    let keybinds = Config::default().keybinds();
    let table: [(ControlScope, [Option<KeybindAction>; 11]); 4] = [
        (
            ControlScope::Tabs,
            [
                Some(NewTab),
                Some(RenameTab),
                Some(CloseTab),
                Some(PreviousTab),
                Some(NextTab),
                None,
                None,
                Some(MoveTabLeft),
                Some(MoveTabRight),
                Some(SwitchTab(1)),
                None,
            ],
        ),
        (
            ControlScope::Spaces,
            [
                Some(NewWorkspace),
                Some(RenameWorkspace),
                Some(CloseWorkspace),
                None,
                None,
                Some(PreviousWorkspace),
                Some(NextWorkspace),
                Some(MoveWorkspaceUp),
                Some(MoveWorkspaceDown),
                Some(SwitchWorkspace(1)),
                None,
            ],
        ),
        (
            ControlScope::Agents,
            [
                None,
                None,
                None,
                None,
                None,
                Some(PreviousAgent),
                Some(NextAgent),
                None,
                None,
                Some(FocusAgent(1)),
                None,
            ],
        ),
        (
            ControlScope::Panes,
            [
                Some(SplitVertical),
                Some(RenamePane),
                Some(ClosePane),
                Some(FocusPaneLeft),
                Some(FocusPaneRight),
                Some(FocusPaneUp),
                Some(FocusPaneDown),
                Some(SwapPaneLeft),
                Some(SwapPaneRight),
                None,
                Some(Zoom),
            ],
        ),
    ];
    let letters = ['n', 'r', 'x', 'h', 'l', 'k', 'j', 'i', 'o', '2', 'z'];
    for (scope, expected) in table {
        for (letter, expected) in letters.into_iter().zip(expected) {
            assert_eq!(
                control_action_for_key(&keybinds, scope, &key(KeyCode::Char(letter)), None),
                expected,
                "{scope:?} {letter:?}"
            );
        }
        // Arrows are global regardless of scope.
        for (code, expected) in [
            (KeyCode::Left, PreviousTab),
            (KeyCode::Right, NextTab),
            (KeyCode::Up, PreviousWorkspace),
            (KeyCode::Down, NextWorkspace),
        ] {
            assert_eq!(
                control_action_for_key(&keybinds, scope, &key(code), None),
                Some(expected),
                "{scope:?} {code:?}"
            );
        }
        assert_eq!(
            control_action_for_key(&keybinds, scope, &key(KeyCode::Char('q')), None),
            None
        );
    }
}

#[test]
fn pane_split_follows_focused_pane_shape_with_split_right_fallback() {
    let keybinds = Config::default().keybinds();
    let split = |rect| {
        control_action_for_key(
            &keybinds,
            ControlScope::Panes,
            &key(KeyCode::Char('n')),
            rect,
        )
    };
    assert_eq!(
        split(Some(Rect::new(0, 0, 80, 20))),
        Some(KeybindAction::SplitVertical)
    );
    assert_eq!(
        split(Some(Rect::new(0, 0, 30, 40))),
        Some(KeybindAction::SplitHorizontal)
    );
    assert_eq!(split(None), Some(KeybindAction::SplitVertical));
}

#[test]
fn tab_scope_navigation_and_reorder_stay_in_mode() {
    let mut state = control_state(ControlScope::Tabs);

    let next = state.handle_input_bytes(b"l");
    assert!(matches!(
        endpoint_methods(&next)[..],
        [Method::TabFocus(target)] if target.tab_id == "tab_2"
    ));
    assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Tabs));

    let switch = state.handle_input_bytes(b"3");
    assert!(matches!(
        endpoint_methods(&switch)[..],
        [Method::TabFocus(target)] if target.tab_id == "tab_3"
    ));
    assert!(endpoint_methods(&state.handle_input_bytes(b"9")).is_empty());
    assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Tabs));

    // tab.move takes a gap index: one step right from 0 inserts at 2.
    let right = state.handle_input_bytes(b"o");
    assert!(matches!(
        endpoint_methods(&right)[..],
        [Method::TabMove(params)] if params.tab_id == "tab_1" && params.insert_index == 2
    ));
    assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Tabs));

    // No wrap: the first tab cannot move further left.
    assert!(endpoint_methods(&state.handle_input_bytes(b"i")).is_empty());
    assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Tabs));
}

#[test]
fn tab_reorder_stops_at_the_last_tab() {
    let mut snapshot = control_snapshot();
    snapshot.focused_tab_id = Some("tab_3".into());
    let mut state = state_with(&Config::default(), snapshot);
    state.mode = ClientShellMode::Control(ControlScope::Tabs);

    assert!(endpoint_methods(&state.handle_input_bytes(b"o")).is_empty());
    let left = state.handle_input_bytes(b"i");
    assert!(matches!(
        endpoint_methods(&left)[..],
        [Method::TabMove(params)] if params.tab_id == "tab_3" && params.insert_index == 1
    ));
}

#[test]
fn create_rename_and_close_leave_the_mode() {
    let mut state = control_state(ControlScope::Tabs);
    state.handle_input_bytes(b"r");
    assert!(matches!(state.overlay, Some(ClientShellOverlay::Rename(_))));
    assert_eq!(state.mode, ClientShellMode::Terminal);

    let mut state = control_state(ControlScope::Tabs);
    state.config.prompt_new_tab_name = false;
    let create = state.handle_input_bytes(b"n");
    assert!(matches!(
        endpoint_methods(&create)[..],
        [Method::TabCreate(_)]
    ));
    assert_eq!(state.mode, ClientShellMode::Terminal);

    let mut state = control_state(ControlScope::Spaces);
    state.handle_input_bytes(b"x");
    assert_eq!(state.mode, ClientShellMode::Terminal);

    let mut state = control_state(ControlScope::Panes);
    let split = state.handle_input_bytes(b"n");
    assert!(matches!(
        endpoint_methods(&split)[..],
        [Method::PaneSplit(params)] if params.direction == SplitDirection::Right
    ));
    assert_eq!(state.mode, ClientShellMode::Terminal);
}

#[test]
fn space_scope_walks_and_moves_standalone_workspaces() {
    let mut state = control_state(ControlScope::Spaces);

    let down = state.handle_input_bytes(b"j");
    assert!(matches!(
        endpoint_methods(&down)[..],
        [Method::WorkspaceFocus(target)] if target.workspace_id == "ws_2"
    ));
    assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Spaces));

    let move_down = state.handle_input_bytes(b"o");
    assert!(matches!(
        endpoint_methods(&move_down)[..],
        [Method::WorkspaceMove(params)] if params.workspace_id == "ws_1" && params.insert_index == 2
    ));
    assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Spaces));

    // Top edge: no wrap.
    assert!(endpoint_methods(&state.handle_input_bytes(b"i")).is_empty());

    let mut snapshot = control_snapshot();
    snapshot.focused_workspace_id = Some("ws_3".into());
    let mut state = state_with(&Config::default(), snapshot);
    state.mode = ClientShellMode::Control(ControlScope::Spaces);
    assert!(endpoint_methods(&state.handle_input_bytes(b"o")).is_empty());
    let up = state.handle_input_bytes(b"i");
    assert!(matches!(
        endpoint_methods(&up)[..],
        [Method::WorkspaceMove(params)] if params.workspace_id == "ws_3" && params.insert_index == 1
    ));
}

#[test]
fn space_scope_moves_worktree_groups_as_blocks() {
    let mut snapshot = control_snapshot();
    // ws_3 becomes a linked worktree of ws_1, so the sidebar roots are
    // [ws_1 (+ws_3), ws_2].
    for (index, linked) in [(0, false), (2, true)] {
        snapshot.workspaces[index].worktree = Some(crate::protocol::ClientShellWorktree {
            key: "repo".into(),
            label: "repo".into(),
            is_linked_worktree: linked,
        });
    }
    let mut state = state_with(&Config::default(), snapshot.clone());
    state.mode = ClientShellMode::Control(ControlScope::Spaces);

    let down = state.handle_input_bytes(b"o");
    assert!(matches!(
        endpoint_methods(&down)[..],
        [Method::WorkspaceMoveBlock(params)]
            if params.workspace_ids == ["ws_1", "ws_3"] && params.before_workspace_id.is_none()
    ));

    snapshot.focused_workspace_id = Some("ws_3".into());
    let mut state = state_with(&Config::default(), snapshot);
    state.mode = ClientShellMode::Control(ControlScope::Spaces);
    assert!(
        endpoint_methods(&state.handle_input_bytes(b"i")).is_empty(),
        "linked worktree children refuse to move, matching the drag path"
    );
}

#[test]
fn agent_scope_walks_agents_and_ignores_object_verbs() {
    let mut state = control_state(ControlScope::Agents);
    let next = state.handle_input_bytes(b"j");
    assert!(matches!(
        endpoint_methods(&next)[..],
        [Method::PaneFocus(target)] if target.pane_id == "pane_2"
    ));
    assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Agents));

    for verb in [b"n", b"r", b"x", b"o"] {
        let outcome = state.handle_input_bytes(verb);
        assert!(endpoint_methods(&outcome).is_empty());
        assert!(state.overlay.is_none());
        assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Agents));
    }
}

#[test]
fn pane_scope_focus_swap_and_zoom_stay_in_mode() {
    let mut state = control_state(ControlScope::Panes);
    let focus = state.handle_input_bytes(b"l");
    assert!(matches!(
        endpoint_methods(&focus)[..],
        [Method::PaneFocusDirection(params)] if params.direction == PaneDirection::Right
    ));
    let swap = state.handle_input_bytes(b"o");
    assert!(matches!(
        endpoint_methods(&swap)[..],
        [Method::PaneSwap(params)] if params.direction == Some(PaneDirection::Right)
    ));
    let zoom = state.handle_input_bytes(b"z");
    assert!(matches!(endpoint_methods(&zoom)[..], [Method::PaneZoom(_)]));
    assert!(endpoint_methods(&state.handle_input_bytes(b"2")).is_empty());
    assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Panes));
}

#[test]
fn scope_keys_switch_without_leaving_and_prefix_chains() {
    let mut state = control_state(ControlScope::Tabs);
    for (letter, scope) in [
        (b"s", ControlScope::Spaces),
        (b"a", ControlScope::Agents),
        (b"p", ControlScope::Panes),
        (b"t", ControlScope::Tabs),
    ] {
        state.handle_input_bytes(letter);
        assert_eq!(state.mode, ClientShellMode::Control(scope));
    }

    assert!(state.handle_input_bytes(b"q").actions.is_empty());
    assert_eq!(
        state.mode,
        ClientShellMode::Control(ControlScope::Tabs),
        "unknown keys are inert"
    );

    state.handle_input_bytes(&[0x02]);
    assert_eq!(state.mode, ClientShellMode::Prefix);
    // The chain lands in a real prefix action, e.g. prefix+f into pane mode.
    state.handle_input_bytes(b"f");
    assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Panes));
}

#[test]
fn entry_bindings_toggle_off_with_scope_switch_precedence() {
    // With defaults, bare t/a are scope switches, not toggles; only the
    // non-letter-clashing shift+s and f rhs keys toggle the mode off.
    let mut state = control_state(ControlScope::Spaces);
    state.handle_input_bytes(b"t");
    assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Tabs));
    state.handle_input_bytes(b"S");
    assert_eq!(state.mode, ClientShellMode::Terminal);
    state.mode = ClientShellMode::Control(ControlScope::Panes);
    state.handle_input_bytes(b"f");
    assert_eq!(state.mode, ClientShellMode::Terminal);

    // Direct entry chords (the personal ctrl+t style) toggle off from any scope.
    let config: Config = toml::from_str("[keys]\ntab_mode = \"ctrl+t\"\n").unwrap();
    let mut state = state_with(&config, control_snapshot());
    state.handle_input_bytes(&[0x14]);
    assert_eq!(state.mode, ClientShellMode::Control(ControlScope::Tabs));
    state.handle_input_bytes(b"p");
    state.handle_input_bytes(&[0x14]);
    assert_eq!(state.mode, ClientShellMode::Terminal);
}

#[test]
fn sticky_set_covers_navigation_and_reorder_only() {
    for action in [
        KeybindAction::NextTab,
        KeybindAction::MoveTabRight,
        KeybindAction::MoveWorkspaceDown,
        KeybindAction::FocusAgent(0),
        KeybindAction::FocusPaneUp,
        KeybindAction::SwapPaneLeft,
        KeybindAction::Zoom,
    ] {
        assert!(control_sticky_action(action), "{action:?}");
    }
    for action in [
        KeybindAction::NewTab,
        KeybindAction::RenameWorkspace,
        KeybindAction::CloseTab,
        KeybindAction::SplitVertical,
        KeybindAction::ClosePane,
    ] {
        assert!(!control_sticky_action(action), "{action:?}");
    }
}

#[test]
fn direct_move_bindings_reorder_tabs_and_workspaces_outside_the_mode() {
    let config: Config = toml::from_str(
        "[keys]\nmove_tab_left = \"alt+i\"\nmove_tab_right = \"alt+o\"\nmove_workspace_down = \"alt+j\"\n",
    )
    .unwrap();
    assert!(config.collect_diagnostics().is_empty());
    let mut state = state_with(&config, control_snapshot());

    let right = state.handle_input_bytes(b"\x1bo");
    assert!(matches!(
        endpoint_methods(&right)[..],
        [Method::TabMove(params)] if params.insert_index == 2
    ));
    assert!(endpoint_methods(&state.handle_input_bytes(b"\x1bi")).is_empty());
    let down = state.handle_input_bytes(b"\x1bj");
    assert!(matches!(
        endpoint_methods(&down)[..],
        [Method::WorkspaceMove(params)] if params.workspace_id == "ws_1"
    ));
    assert_eq!(state.mode, ClientShellMode::Terminal);
}

#[test]
fn entry_on_mobile_opens_the_switcher_instead() {
    let mut state = state_with(&Config::default(), control_snapshot());
    state.compose(44, 30).expect("mobile frame");
    assert!(state.mobile_layout_active());
    state.handle_input_bytes(&[0x02]);
    state.handle_input_bytes(b"t");
    assert_eq!(state.mode, ClientShellMode::Navigate);
}

fn frame_text(state: &mut ClientShellState, cols: u16, rows: u16) -> Vec<String> {
    frame_rows(&state.compose(cols, rows).expect("frame"))
}

#[test]
fn scoped_mode_bars_render_per_scope_and_tab_bar_position() {
    for (scope, badge, present, absent) in [
        (
            ControlScope::Tabs,
            "TABS",
            &["h/l", "prev/next", "1-9"][..],
            &["k/j"][..],
        ),
        (ControlScope::Spaces, "SPACES", &["k/j", "1-9"], &["h/l"]),
        (
            ControlScope::Agents,
            "AGENTS",
            &["k/j", "1-9"],
            &["rename", "h/l"],
        ),
        (
            ControlScope::Panes,
            "PANES",
            &["h/j/k/l", "focus", "split", "zoom"],
            &["1-9"],
        ),
    ] {
        let mut state = control_state(scope);
        let rows = frame_text(&mut state, 160, 20);
        let bar = rows
            .iter()
            .find(|row| row.contains(badge))
            .unwrap_or_else(|| panic!("{badge} bar missing: {rows:?}"));
        for text in present {
            assert!(bar.contains(text), "{badge}: {text} missing from {bar:?}");
        }
        for text in absent {
            assert!(!bar.contains(text), "{badge}: {text} present in {bar:?}");
        }
    }

    let mut state = control_state(ControlScope::Tabs);
    state.config.tab_bar_position = crate::config::TabBarPositionConfig::Bottom;
    let rows = frame_text(&mut state, 106, 20);
    assert!(rows[19].contains("TABS"), "bottom bar: {:?}", rows[19]);
    assert!(state.hits.tabs.is_empty(), "the bar replaces the tab row");

    // Narrow terminals clip on the right; the badge stays and nothing panics.
    let mut state = control_state(ControlScope::Panes);
    let rows = frame_text(&mut state, 70, 12);
    assert!(rows.iter().any(|row| row.contains("PANES")));
}
