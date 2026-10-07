use super::*;
use crate::config::Keybinds;
use crate::input::{KeybindAction, KeybindMatch};

pub(super) fn control_scope_for_entry(action: KeybindAction) -> Option<ControlScope> {
    match action {
        KeybindAction::EnterTabMode => Some(ControlScope::Tabs),
        KeybindAction::EnterSpaceMode => Some(ControlScope::Spaces),
        KeybindAction::EnterAgentMode => Some(ControlScope::Agents),
        KeybindAction::EnterPaneMode => Some(ControlScope::Panes),
        _ => None,
    }
}

impl ClientShellState {
    pub(super) fn route_control_key(
        &mut self,
        scope: ControlScope,
        key: &crate::input::TerminalKey,
        outcome: &mut ClientShellInput,
    ) {
        // Unlike resize mode, the prefix chains into prefix mode instead of
        // staying inert, so `tab mode -> prefix+c` works without an explicit exit.
        if self.config.keybinds.matches_prefix(key) {
            self.mode = ClientShellMode::Prefix;
            outcome.repaint = true;
            return;
        }

        let keybinds = &self.config.keybinds.keybinds;
        // Scope switches win over the entry-binding toggle: with the default
        // `tab_mode = "prefix+t"` the bare letter is both the toggle rhs and the
        // tabs scope key, and switching is the useful reading.
        if let Some(next) = control_scope_for_key(keybinds, key) {
            self.mode = ClientShellMode::Control(next);
            outcome.repaint = true;
            return;
        }

        if key.code == KeyCode::Esc
            || key.code == KeyCode::Enter
            || control_entry_binding_matches(keybinds, key)
        {
            self.mode = self.copy_or_terminal_mode();
            outcome.repaint = true;
            return;
        }

        let Some(action) = control_action_for_key(keybinds, scope, key, self.focused_pane_rect())
        else {
            // Unknown keys are inert, matching resize mode's tolerance.
            return;
        };
        let binding = KeybindMatch::Action(action);
        if !self.indexed_navigation_target_exists(&binding) {
            return;
        }
        if !control_sticky_action(action) {
            self.mode = self.copy_or_terminal_mode();
        }
        self.record_binding(binding, outcome);
        outcome.repaint = true;
    }

    fn focused_pane_rect(&self) -> Option<Rect> {
        let focused = self.snapshot.as_deref()?.focused_pane_id.as_deref()?;
        self.hits
            .panes
            .iter()
            .find(|pane| pane.pane_id == focused)
            .map(|pane| pane.rect)
    }
}

/// Any of the four entry bindings toggles the mode off from inside it.
fn control_entry_binding_matches(keybinds: &Keybinds, key: &crate::input::TerminalKey) -> bool {
    [
        &keybinds.tab_mode,
        &keybinds.space_mode,
        &keybinds.agent_mode,
        &keybinds.pane_mode,
    ]
    .into_iter()
    .any(|bindings| bindings.matches_prefix_key(key) || bindings.matches_direct_key(key))
}

fn control_scope_for_key(
    keybinds: &Keybinds,
    key: &crate::input::TerminalKey,
) -> Option<ControlScope> {
    let control = &keybinds.control;
    [
        (&control.scope_tabs, ControlScope::Tabs),
        (&control.scope_spaces, ControlScope::Spaces),
        (&control.scope_agents, ControlScope::Agents),
        (&control.scope_panes, ControlScope::Panes),
    ]
    .into_iter()
    .find_map(|(bindings, scope)| bindings.matches_direct_key(key).then_some(scope))
}

pub(super) fn control_action_for_key(
    keybinds: &Keybinds,
    scope: ControlScope,
    key: &crate::input::TerminalKey,
    focused_pane_rect: Option<Rect>,
) -> Option<KeybindAction> {
    use ControlScope::{Agents, Panes, Spaces, Tabs};

    if let Some(index) = ('1'..='9').position(|digit| {
        crate::config::terminal_key_matches_combo(
            key,
            (
                KeyCode::Char(digit),
                crossterm::event::KeyModifiers::empty(),
            ),
        )
    }) {
        // Panes carry no visible ordinals, so indexed focus would be a blind
        // misfire; digits are deliberately inert there.
        return match scope {
            Tabs => Some(KeybindAction::SwitchTab(index)),
            Spaces => Some(KeybindAction::SwitchWorkspace(index)),
            Agents => Some(KeybindAction::FocusAgent(index)),
            Panes => None,
        };
    }

    let control = &keybinds.control;
    // Navigation splits by orientation: previous/next (h/l) walk the horizontal
    // tab row, up/down (k/j) walk the vertical space and agent lists, and the
    // off-axis pair is inert. Panes are 2D and take all four as focus moves.
    let verbs: [(&crate::config::ActionKeybinds, [Option<KeybindAction>; 4]); 10] = [
        (
            &control.new,
            [
                Some(KeybindAction::NewTab),
                Some(KeybindAction::NewWorkspace),
                None,
                Some(auto_split_action(focused_pane_rect)),
            ],
        ),
        (
            &control.rename,
            [
                Some(KeybindAction::RenameTab),
                Some(KeybindAction::RenameWorkspace),
                None,
                Some(KeybindAction::RenamePane),
            ],
        ),
        (
            &control.close,
            [
                Some(KeybindAction::CloseTab),
                Some(KeybindAction::CloseWorkspace),
                None,
                Some(KeybindAction::ClosePane),
            ],
        ),
        (
            &control.previous,
            [
                Some(KeybindAction::PreviousTab),
                None,
                None,
                Some(KeybindAction::FocusPaneLeft),
            ],
        ),
        (
            &control.next,
            [
                Some(KeybindAction::NextTab),
                None,
                None,
                Some(KeybindAction::FocusPaneRight),
            ],
        ),
        (
            &control.up,
            [
                None,
                Some(KeybindAction::PreviousWorkspace),
                Some(KeybindAction::PreviousAgent),
                Some(KeybindAction::FocusPaneUp),
            ],
        ),
        (
            &control.down,
            [
                None,
                Some(KeybindAction::NextWorkspace),
                Some(KeybindAction::NextAgent),
                Some(KeybindAction::FocusPaneDown),
            ],
        ),
        (
            &control.move_back,
            [
                Some(KeybindAction::MoveTabLeft),
                Some(KeybindAction::MoveWorkspaceUp),
                None,
                Some(KeybindAction::SwapPaneLeft),
            ],
        ),
        (
            &control.move_forward,
            [
                Some(KeybindAction::MoveTabRight),
                Some(KeybindAction::MoveWorkspaceDown),
                None,
                Some(KeybindAction::SwapPaneRight),
            ],
        ),
        (&control.zoom, [None, None, None, Some(KeybindAction::Zoom)]),
    ];
    let column = match scope {
        Tabs => 0,
        Spaces => 1,
        Agents => 2,
        Panes => 3,
    };
    if let Some((_, actions)) = verbs
        .iter()
        .find(|(bindings, _)| bindings.matches_direct_key(key))
    {
        return actions[column];
    }

    // Arrows stay global in every scope: left/right walk tabs, up/down walk
    // workspaces, mirroring navigate mode's permanent-alias contract.
    let (code, modifiers) = crate::config::normalize_key_combo((key.code, key.modifiers));
    if !modifiers.is_empty() {
        return None;
    }
    match code {
        KeyCode::Left => Some(KeybindAction::PreviousTab),
        KeyCode::Right => Some(KeybindAction::NextTab),
        KeyCode::Up => Some(KeybindAction::PreviousWorkspace),
        KeyCode::Down => Some(KeybindAction::NextWorkspace),
        _ => None,
    }
}

/// Split direction for the panes-scope `new` verb: right when the focused pane
/// is wide, down when tall. Cells are roughly twice as tall as wide, so a pane
/// reads as wide when width >= 2x height. Without a rendered rect, split right
/// (zellij's fixed default); a zoomed pane reports the full area and splits right.
fn auto_split_action(focused_pane_rect: Option<Rect>) -> KeybindAction {
    match focused_pane_rect {
        Some(rect) if u32::from(rect.width) < u32::from(rect.height) * 2 => {
            KeybindAction::SplitHorizontal
        }
        _ => KeybindAction::SplitVertical,
    }
}

/// Actions that keep the mode active. Everything that creates, renames, or
/// closes leaves it, matching zellij's tab mode.
pub(super) fn control_sticky_action(action: KeybindAction) -> bool {
    matches!(
        action,
        KeybindAction::SwitchTab(_)
            | KeybindAction::SwitchWorkspace(_)
            | KeybindAction::FocusAgent(_)
            | KeybindAction::PreviousTab
            | KeybindAction::NextTab
            | KeybindAction::MoveTabLeft
            | KeybindAction::MoveTabRight
            | KeybindAction::PreviousWorkspace
            | KeybindAction::NextWorkspace
            | KeybindAction::MoveWorkspaceUp
            | KeybindAction::MoveWorkspaceDown
            | KeybindAction::PreviousAgent
            | KeybindAction::NextAgent
            | KeybindAction::FocusPaneLeft
            | KeybindAction::FocusPaneDown
            | KeybindAction::FocusPaneUp
            | KeybindAction::FocusPaneRight
            | KeybindAction::SwapPaneLeft
            | KeybindAction::SwapPaneRight
            | KeybindAction::Zoom
    )
}
