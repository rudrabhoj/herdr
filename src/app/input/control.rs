use crossterm::event::KeyCode;

use crate::input::TerminalKey;

use super::navigate::{
    leave_command_mode, unmodified_digit_for_key, ActionContext, NavigateAction,
};
use crate::app::{
    state::{AppState, ControlScope, Mode},
    App,
};

impl App {
    pub(crate) fn handle_control_key(&mut self, raw_key: TerminalKey) {
        let key = raw_key.as_key_event();
        self.state.update_dismissed = true;

        if matches!(key.code, KeyCode::Modifier(_)) {
            return;
        }

        // Divergence from the resize template: the prefix key chains into
        // prefix mode instead of staying inert, so `tab mode -> prefix+c`
        // works without an explicit exit.
        if self.state.is_prefix_key(&raw_key) {
            self.state.mode = Mode::Prefix;
            return;
        }

        // Scope switches win over the entry-binding toggle: with the default
        // `tab_mode = "prefix+t"` the bare letter is both the toggle rhs and
        // the tabs scope key, and switching is the useful reading. esc/enter
        // always exit.
        if let Some(scope) = control_scope_for_key(&self.state, &raw_key) {
            self.state.control_scope = scope;
            return;
        }

        if key.code == KeyCode::Esc
            || key.code == KeyCode::Enter
            || control_entry_binding_matches(&self.state, &raw_key)
        {
            leave_command_mode(&mut self.state);
            return;
        }

        if let Some(action) = control_action_for_key(&self.state, &raw_key) {
            self.execute_control_action(action);
        }
        // Unknown keys are inert, matching resize mode's tolerance.
    }

    fn execute_control_action(&mut self, action: NavigateAction) {
        self.execute_tui_navigate_action(action, ActionContext::Control);
        // The navigation arms land in Terminal via leave_navigate_mode; sticky
        // actions restore the mode afterwards. Modal transitions (rename,
        // confirm-close) never land in Terminal and stay untouched; create and
        // close leave the mode by omission from the sticky set.
        if control_sticky_action(action) && self.state.mode == Mode::Terminal {
            self.state.mode = Mode::Control;
        }
    }
}

/// Any of the four entry bindings toggles the mode off from inside it.
fn control_entry_binding_matches(state: &AppState, key: &TerminalKey) -> bool {
    for bindings in [
        &state.keybinds.tab_mode,
        &state.keybinds.space_mode,
        &state.keybinds.agent_mode,
        &state.keybinds.pane_mode,
    ] {
        if bindings.matches_prefix_key(key) || bindings.matches_direct_key(key) {
            return true;
        }
    }
    false
}

fn control_scope_for_key(state: &AppState, key: &TerminalKey) -> Option<ControlScope> {
    let kb = &state.keybinds.control;
    for (bindings, scope) in [
        (&kb.scope_tabs, ControlScope::Tabs),
        (&kb.scope_spaces, ControlScope::Spaces),
        (&kb.scope_agents, ControlScope::Agents),
        (&kb.scope_panes, ControlScope::Panes),
    ] {
        if bindings.matches_direct_key(key) {
            return Some(scope);
        }
    }
    None
}

pub(super) fn control_action_for_key(
    state: &AppState,
    key: &TerminalKey,
) -> Option<NavigateAction> {
    let scope = state.control_scope;

    if let Some(digit) = unmodified_digit_for_key(key) {
        let idx = (digit as usize) - ('1' as usize);
        // Panes carry no visible ordinals, so indexed focus would be a blind
        // misfire; digits are deliberately inert there.
        return match scope {
            ControlScope::Tabs => Some(NavigateAction::SwitchTab(idx)),
            ControlScope::Spaces => Some(NavigateAction::SwitchWorkspace(idx)),
            ControlScope::Agents => Some(NavigateAction::FocusAgent(idx)),
            ControlScope::Panes => None,
        };
    }

    let kb = &state.keybinds.control;
    if kb.new.matches_direct_key(key) {
        return match scope {
            ControlScope::Tabs => Some(NavigateAction::NewTab),
            ControlScope::Spaces => Some(NavigateAction::NewWorkspace),
            ControlScope::Agents => None,
            ControlScope::Panes => Some(auto_split_action(state)),
        };
    }
    if kb.rename.matches_direct_key(key) {
        return match scope {
            ControlScope::Tabs => Some(NavigateAction::RenameTab),
            ControlScope::Spaces => Some(NavigateAction::RenameWorkspace),
            ControlScope::Agents => None,
            ControlScope::Panes => Some(NavigateAction::RenamePane),
        };
    }
    if kb.close.matches_direct_key(key) {
        return match scope {
            ControlScope::Tabs => Some(NavigateAction::CloseTab),
            ControlScope::Spaces => Some(NavigateAction::CloseWorkspace),
            ControlScope::Agents => None,
            ControlScope::Panes => Some(NavigateAction::ClosePane),
        };
    }
    // Navigation splits by orientation: previous/next (h/l) walk the
    // horizontal tab row, up/down (k/j) walk the vertical space and agent
    // lists. The off-axis pair is inert in each scope.
    if kb.previous.matches_direct_key(key) {
        return match scope {
            ControlScope::Tabs => Some(NavigateAction::PreviousTab),
            ControlScope::Spaces | ControlScope::Agents => None,
            ControlScope::Panes => Some(NavigateAction::FocusPaneLeft),
        };
    }
    if kb.next.matches_direct_key(key) {
        return match scope {
            ControlScope::Tabs => Some(NavigateAction::NextTab),
            ControlScope::Spaces | ControlScope::Agents => None,
            ControlScope::Panes => Some(NavigateAction::FocusPaneRight),
        };
    }
    if kb.up.matches_direct_key(key) {
        return match scope {
            ControlScope::Tabs => None,
            ControlScope::Spaces => Some(NavigateAction::PreviousWorkspace),
            ControlScope::Agents => Some(NavigateAction::PreviousAgent),
            ControlScope::Panes => Some(NavigateAction::FocusPaneUp),
        };
    }
    if kb.down.matches_direct_key(key) {
        return match scope {
            ControlScope::Tabs => None,
            ControlScope::Spaces => Some(NavigateAction::NextWorkspace),
            ControlScope::Agents => Some(NavigateAction::NextAgent),
            ControlScope::Panes => Some(NavigateAction::FocusPaneDown),
        };
    }
    if kb.move_back.matches_direct_key(key) {
        return match scope {
            ControlScope::Tabs => Some(NavigateAction::MoveTabLeft),
            ControlScope::Spaces => Some(NavigateAction::MoveWorkspaceUp),
            ControlScope::Agents => None,
            ControlScope::Panes => Some(NavigateAction::SwapPaneLeft),
        };
    }
    if kb.move_forward.matches_direct_key(key) {
        return match scope {
            ControlScope::Tabs => Some(NavigateAction::MoveTabRight),
            ControlScope::Spaces => Some(NavigateAction::MoveWorkspaceDown),
            ControlScope::Agents => None,
            ControlScope::Panes => Some(NavigateAction::SwapPaneRight),
        };
    }
    if kb.zoom.matches_direct_key(key) {
        return match scope {
            ControlScope::Panes => Some(NavigateAction::Zoom),
            ControlScope::Tabs | ControlScope::Spaces | ControlScope::Agents => None,
        };
    }

    // Arrows stay global in every scope: left/right walk tabs, up/down walk
    // workspaces, mirroring navigate mode's permanent-alias contract.
    let (code, modifiers) = crate::config::normalize_key_combo((key.code, key.modifiers));
    if modifiers.is_empty() {
        match code {
            KeyCode::Left => return Some(NavigateAction::PreviousTab),
            KeyCode::Right => return Some(NavigateAction::NextTab),
            KeyCode::Up => return Some(NavigateAction::PreviousWorkspace),
            KeyCode::Down => return Some(NavigateAction::NextWorkspace),
            _ => {}
        }
    }

    None
}

/// Split direction for the panes-scope `n`: right when the focused pane's
/// rendered rect is wide, down when tall. Terminal cells are roughly twice as
/// tall as wide, so a pane reads as "wide" when width >= 2x height in cells.
/// With no focused-pane rect (before the first layout pass, or pure-state
/// tests) default to SplitVertical - split right, zellij's fixed default. A
/// zoomed pane reports the full terminal rect and therefore splits right.
fn auto_split_action(state: &AppState) -> NavigateAction {
    let focused_rect = state
        .view
        .pane_infos
        .iter()
        .find(|pane| pane.is_focused)
        .map(|pane| pane.rect);
    match focused_rect {
        Some(rect) if u32::from(rect.width) < u32::from(rect.height) * 2 => {
            NavigateAction::SplitHorizontal
        }
        _ => NavigateAction::SplitVertical,
    }
}

/// Actions that keep the mode active after executing. Everything that creates,
/// renames, or closes leaves the mode, matching zellij's tab-mode split.
pub(super) fn control_sticky_action(action: NavigateAction) -> bool {
    matches!(
        action,
        NavigateAction::SwitchTab(_)
            | NavigateAction::SwitchWorkspace(_)
            | NavigateAction::FocusAgent(_)
            | NavigateAction::PreviousTab
            | NavigateAction::NextTab
            | NavigateAction::MoveTabLeft
            | NavigateAction::MoveTabRight
            | NavigateAction::PreviousWorkspace
            | NavigateAction::NextWorkspace
            | NavigateAction::MoveWorkspaceUp
            | NavigateAction::MoveWorkspaceDown
            | NavigateAction::PreviousAgent
            | NavigateAction::NextAgent
            | NavigateAction::FocusPaneLeft
            | NavigateAction::FocusPaneDown
            | NavigateAction::FocusPaneUp
            | NavigateAction::FocusPaneRight
            | NavigateAction::SwapPaneLeft
            | NavigateAction::SwapPaneDown
            | NavigateAction::SwapPaneUp
            | NavigateAction::SwapPaneRight
            | NavigateAction::Zoom
    )
}

#[cfg(test)]
mod tests {
    use crossterm::event::{KeyCode, KeyModifiers};

    use super::*;
    use crate::app::state::ViewLayout;
    use crate::config::Config;
    use crate::workspace::Workspace;

    fn app_with_workspaces(names: &[&str]) -> App {
        let (_api_tx, api_rx) = tokio::sync::mpsc::unbounded_channel();
        let mut app = App::new(
            &Config::default(),
            true,
            None,
            api_rx,
            crate::api::EventHub::default(),
        );
        app.state.workspaces = names.iter().map(|name| Workspace::test_new(name)).collect();
        app.state.ensure_test_terminals();
        app.state.active = (!app.state.workspaces.is_empty()).then_some(0);
        app.state.selected = 0;
        app.state.mode = Mode::Control;
        app.state.control_scope = ControlScope::Tabs;
        app
    }

    fn plain(code: KeyCode) -> TerminalKey {
        TerminalKey::new(code, KeyModifiers::empty())
    }

    type VerbCase = (KeyCode, Option<NavigateAction>);

    #[test]
    fn entry_bindings_set_mode_and_scope_and_mobile_opens_panel() {
        let mut app = app_with_workspaces(&["ws"]);
        for (action, scope) in [
            (NavigateAction::EnterTabMode, ControlScope::Tabs),
            (NavigateAction::EnterSpaceMode, ControlScope::Spaces),
            (NavigateAction::EnterAgentMode, ControlScope::Agents),
            (NavigateAction::EnterPaneMode, ControlScope::Panes),
        ] {
            app.state.mode = Mode::Terminal;
            app.execute_tui_navigate_action(action, ActionContext::Prefix);
            assert_eq!(app.state.mode, Mode::Control);
            assert_eq!(app.state.control_scope, scope);
        }

        app.state.mode = Mode::Terminal;
        app.state.view.layout = ViewLayout::Mobile;
        app.execute_tui_navigate_action(NavigateAction::EnterTabMode, ActionContext::Prefix);
        assert_eq!(app.state.mode, Mode::Navigate);
    }

    #[test]
    fn shared_verbs_dispatch_per_scope() {
        let mut app = app_with_workspaces(&["ws"]);
        let cases: [(ControlScope, &[VerbCase]); 3] = [
            (
                ControlScope::Tabs,
                &[
                    (KeyCode::Char('n'), Some(NavigateAction::NewTab)),
                    (KeyCode::Char('r'), Some(NavigateAction::RenameTab)),
                    (KeyCode::Char('x'), Some(NavigateAction::CloseTab)),
                    (KeyCode::Char('h'), Some(NavigateAction::PreviousTab)),
                    (KeyCode::Char('l'), Some(NavigateAction::NextTab)),
                    (KeyCode::Char('k'), None),
                    (KeyCode::Char('j'), None),
                    (KeyCode::Char('i'), Some(NavigateAction::MoveTabLeft)),
                    (KeyCode::Char('o'), Some(NavigateAction::MoveTabRight)),
                    (KeyCode::Char('2'), Some(NavigateAction::SwitchTab(1))),
                    (KeyCode::Char('z'), None),
                ],
            ),
            (
                ControlScope::Spaces,
                &[
                    (KeyCode::Char('n'), Some(NavigateAction::NewWorkspace)),
                    (KeyCode::Char('r'), Some(NavigateAction::RenameWorkspace)),
                    (KeyCode::Char('x'), Some(NavigateAction::CloseWorkspace)),
                    (KeyCode::Char('h'), None),
                    (KeyCode::Char('l'), None),
                    (KeyCode::Char('k'), Some(NavigateAction::PreviousWorkspace)),
                    (KeyCode::Char('j'), Some(NavigateAction::NextWorkspace)),
                    (KeyCode::Char('i'), Some(NavigateAction::MoveWorkspaceUp)),
                    (KeyCode::Char('o'), Some(NavigateAction::MoveWorkspaceDown)),
                    (KeyCode::Char('2'), Some(NavigateAction::SwitchWorkspace(1))),
                    (KeyCode::Char('z'), None),
                ],
            ),
            (
                ControlScope::Agents,
                &[
                    (KeyCode::Char('n'), None),
                    (KeyCode::Char('r'), None),
                    (KeyCode::Char('x'), None),
                    (KeyCode::Char('h'), None),
                    (KeyCode::Char('l'), None),
                    (KeyCode::Char('k'), Some(NavigateAction::PreviousAgent)),
                    (KeyCode::Char('j'), Some(NavigateAction::NextAgent)),
                    (KeyCode::Char('i'), None),
                    (KeyCode::Char('o'), None),
                    (KeyCode::Char('2'), Some(NavigateAction::FocusAgent(1))),
                    (KeyCode::Char('z'), None),
                ],
            ),
        ];
        let panes_row: &[VerbCase] = &[
            (KeyCode::Char('n'), Some(NavigateAction::SplitVertical)),
            (KeyCode::Char('r'), Some(NavigateAction::RenamePane)),
            (KeyCode::Char('x'), Some(NavigateAction::ClosePane)),
            (KeyCode::Char('h'), Some(NavigateAction::FocusPaneLeft)),
            (KeyCode::Char('l'), Some(NavigateAction::FocusPaneRight)),
            (KeyCode::Char('k'), Some(NavigateAction::FocusPaneUp)),
            (KeyCode::Char('j'), Some(NavigateAction::FocusPaneDown)),
            (KeyCode::Char('i'), Some(NavigateAction::SwapPaneLeft)),
            (KeyCode::Char('o'), Some(NavigateAction::SwapPaneRight)),
            (KeyCode::Char('z'), Some(NavigateAction::Zoom)),
            (KeyCode::Char('2'), None),
        ];
        let cases = cases.into_iter().chain([(ControlScope::Panes, panes_row)]);
        for (scope, table) in cases {
            app.state.control_scope = scope;
            for (code, expected) in table {
                assert_eq!(
                    control_action_for_key(&app.state, &plain(*code)),
                    *expected,
                    "{scope:?} {code:?}"
                );
            }
            // Arrows are global regardless of scope.
            assert_eq!(
                control_action_for_key(&app.state, &plain(KeyCode::Left)),
                Some(NavigateAction::PreviousTab)
            );
            assert_eq!(
                control_action_for_key(&app.state, &plain(KeyCode::Down)),
                Some(NavigateAction::NextWorkspace)
            );
        }
    }

    #[test]
    fn scope_switch_keys_change_scope_and_stay_in_mode() {
        let mut app = app_with_workspaces(&["ws"]);
        app.handle_control_key(plain(KeyCode::Char('s')));
        assert_eq!(app.state.mode, Mode::Control);
        assert_eq!(app.state.control_scope, ControlScope::Spaces);

        app.handle_control_key(plain(KeyCode::Char('a')));
        assert_eq!(app.state.control_scope, ControlScope::Agents);

        app.handle_control_key(plain(KeyCode::Char('p')));
        assert_eq!(app.state.control_scope, ControlScope::Panes);

        app.handle_control_key(plain(KeyCode::Char('t')));
        assert_eq!(app.state.control_scope, ControlScope::Tabs);
    }

    #[test]
    fn navigation_keys_keep_the_mode_sticky() {
        let mut app = app_with_workspaces(&["one", "two"]);
        app.state.workspaces[0].test_add_tab(Some("second"));
        app.state.ensure_test_terminals();

        app.handle_control_key(plain(KeyCode::Char('l')));
        assert_eq!(app.state.mode, Mode::Control, "next tab stays in mode");

        app.handle_control_key(plain(KeyCode::Char('1')));
        assert_eq!(
            app.state.mode,
            Mode::Control,
            "indexed switch stays in mode"
        );

        app.handle_control_key(plain(KeyCode::Char('o')));
        assert_eq!(app.state.mode, Mode::Control, "tab reorder stays in mode");

        app.state.control_scope = ControlScope::Spaces;
        app.handle_control_key(plain(KeyCode::Char('j')));
        assert_eq!(
            app.state.mode,
            Mode::Control,
            "workspace switch down stays in mode"
        );
        app.handle_control_key(plain(KeyCode::Char('k')));
        assert_eq!(
            app.state.mode,
            Mode::Control,
            "workspace switch up stays in mode"
        );
    }

    #[test]
    fn mutating_keys_leave_the_mode_appropriately() {
        let mut app = app_with_workspaces(&["one"]);
        app.state.workspaces[0].test_add_tab(Some("second"));
        app.state.ensure_test_terminals();

        app.handle_control_key(plain(KeyCode::Char('r')));
        assert_eq!(app.state.mode, Mode::RenameTab, "rename opens its modal");

        app.state.mode = Mode::Control;
        app.state.control_scope = ControlScope::Spaces;
        app.state.confirm_close = true;
        app.handle_control_key(plain(KeyCode::Char('x')));
        assert_eq!(
            app.state.mode,
            Mode::ConfirmClose,
            "close workspace honors confirm_close"
        );

        app.state.mode = Mode::Control;
        app.state.control_scope = ControlScope::Tabs;
        app.handle_control_key(plain(KeyCode::Char('x')));
        assert_eq!(
            app.state.mode,
            Mode::Terminal,
            "close tab leaves the mode by omission from the sticky set"
        );
    }

    #[test]
    fn exit_keys_leave_and_prefix_chains_into_prefix_mode() {
        let mut app = app_with_workspaces(&["ws"]);
        app.handle_control_key(plain(KeyCode::Esc));
        assert_eq!(app.state.mode, Mode::Terminal);

        app.state.mode = Mode::Control;
        app.handle_control_key(plain(KeyCode::Enter));
        assert_eq!(app.state.mode, Mode::Terminal);

        // Real chain: control -> prefix (ctrl+b) -> t re-enters tab mode.
        app.state.mode = Mode::Prefix;
        app.execute_tui_navigate_action(NavigateAction::EnterTabMode, ActionContext::Prefix);
        assert_eq!(app.state.mode, Mode::Control);

        app.state.mode = Mode::Control;
        app.handle_control_key(TerminalKey::new(KeyCode::Char('b'), KeyModifiers::CONTROL));
        assert_eq!(
            app.state.mode,
            Mode::Prefix,
            "prefix key chains into prefix mode"
        );
    }

    #[test]
    fn entry_bindings_toggle_off_with_scope_switch_precedence() {
        let mut app = app_with_workspaces(&["ws"]);
        // Direct-form entry binding (the personal ctrl+t style) exits from inside.
        app.state.keybinds.tab_mode = crate::config::ActionKeybinds::direct("ctrl+t");
        app.handle_control_key(TerminalKey::new(KeyCode::Char('t'), KeyModifiers::CONTROL));
        assert_eq!(
            app.state.mode,
            Mode::Terminal,
            "direct entry binding toggles off"
        );

        // With defaults, scope switches win over the prefix-rhs toggle: bare t/a
        // switch scope, and only space_mode's shift+s rhs actually exits.
        let mut app = app_with_workspaces(&["ws"]);
        app.handle_control_key(plain(KeyCode::Char('t')));
        assert_eq!(app.state.mode, Mode::Control);
        assert_eq!(app.state.control_scope, ControlScope::Tabs);
        app.handle_control_key(plain(KeyCode::Char('a')));
        assert_eq!(app.state.mode, Mode::Control);
        assert_eq!(app.state.control_scope, ControlScope::Agents);
        app.handle_control_key(TerminalKey::new(KeyCode::Char('s'), KeyModifiers::SHIFT));
        assert_eq!(
            app.state.mode,
            Mode::Terminal,
            "space_mode rhs shift+s is no scope letter and toggles off"
        );

        let mut app = app_with_workspaces(&["ws"]);
        app.state.control_scope = ControlScope::Panes;
        app.handle_control_key(plain(KeyCode::Char('f')));
        assert_eq!(
            app.state.mode,
            Mode::Terminal,
            "pane_mode rhs f is no scope letter and toggles off"
        );
    }

    #[test]
    fn unknown_keys_are_inert_and_empty_state_exits_to_navigate() {
        let mut app = app_with_workspaces(&["ws"]);
        app.handle_control_key(plain(KeyCode::Char('q')));
        assert_eq!(app.state.mode, Mode::Control, "unknown keys do not exit");

        let mut empty = app_with_workspaces(&[]);
        empty.handle_control_key(plain(KeyCode::Esc));
        assert_eq!(
            empty.state.mode,
            Mode::Navigate,
            "no focused workspace exits to navigate"
        );
    }

    #[test]
    fn auto_split_follows_focused_pane_shape_with_split_right_fallback() {
        use ratatui::layout::Rect;
        let mut app = app_with_workspaces(&["ws"]);
        app.state.control_scope = ControlScope::Panes;
        let pane_id = app.state.workspaces[0].tabs[0].root_pane;
        let pane_info = |rect: Rect| crate::layout::PaneInfo {
            id: pane_id,
            rect,
            inner_rect: rect,
            scrollbar_rect: None,
            borders: ratatui::widgets::Borders::NONE,
            is_focused: true,
        };

        // Wide pane (width >= 2x height in cells): split right.
        app.state.view.pane_infos = vec![pane_info(Rect::new(0, 0, 80, 20))];
        assert_eq!(
            control_action_for_key(&app.state, &plain(KeyCode::Char('n'))),
            Some(NavigateAction::SplitVertical)
        );

        // Tall pane: split down.
        app.state.view.pane_infos = vec![pane_info(Rect::new(0, 0, 30, 40))];
        assert_eq!(
            control_action_for_key(&app.state, &plain(KeyCode::Char('n'))),
            Some(NavigateAction::SplitHorizontal)
        );

        // No focused rect: SplitVertical fallback (zellij's fixed default).
        app.state.view.pane_infos.clear();
        assert_eq!(
            control_action_for_key(&app.state, &plain(KeyCode::Char('n'))),
            Some(NavigateAction::SplitVertical)
        );
    }

    #[tokio::test]
    async fn pane_focus_and_swap_and_zoom_keep_the_mode_sticky() {
        let mut app = app_with_workspaces(&["ws"]);
        app.state.control_scope = ControlScope::Panes;

        app.handle_control_key(plain(KeyCode::Char('l')));
        assert_eq!(app.state.mode, Mode::Control, "focus stays in mode");

        app.handle_control_key(plain(KeyCode::Char('o')));
        assert_eq!(app.state.mode, Mode::Control, "swap stays in mode");

        app.handle_control_key(plain(KeyCode::Char('z')));
        assert_eq!(app.state.mode, Mode::Control, "zoom stays in mode");

        app.handle_control_key(plain(KeyCode::Char('n')));
        assert_eq!(
            app.state.mode,
            Mode::Terminal,
            "split leaves the mode per the create-leaves rule"
        );
    }

    #[test]
    fn control_mode_survives_adversarial_state_walk() {
        let (_api_tx, api_rx) = tokio::sync::mpsc::unbounded_channel();
        let mut app = App::new(
            &Config::default(),
            true,
            None,
            api_rx,
            crate::api::EventHub::default(),
        );
        app.state = crate::app::AppState::test_with_adversarial_identity_state();
        app.state.mode = Mode::Control;
        for scope in [
            ControlScope::Tabs,
            ControlScope::Spaces,
            ControlScope::Agents,
            ControlScope::Panes,
        ] {
            app.state.control_scope = scope;
            for key in [
                plain(KeyCode::Char('l')),
                plain(KeyCode::Char('o')),
                plain(KeyCode::Char('x')),
                plain(KeyCode::Char('z')),
                plain(KeyCode::Char('p')),
                plain(KeyCode::Char('s')),
            ] {
                app.state.mode = Mode::Control;
                app.handle_control_key(key);
                app.state.assert_invariants_for_test();
            }
        }
    }
}
