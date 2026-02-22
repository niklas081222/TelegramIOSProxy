import Foundation
import Display
import TelegramPresentationData
import AccountContext
import TelegramCore

/// A navigation bar button that toggles AI translation for the current chat.
/// Shows "AI" text that is highlighted when translation is active.
public final class AITranslationToggleButton {
    /// Creates a UIBarButtonItem for toggling AI translation in a chat.
    public static func createBarButtonItem(
        peerId: PeerId,
        presentationData: PresentationData,
        action: @escaping () -> Void
    ) -> UIBarButtonItem {
        let isEnabled = AITranslationService.shared.isEnabledForChat(peerId)

        let button = UIButton(type: .system)
        button.setTitle("AI", for: .normal)

        if isEnabled {
            button.setTitleColor(presentationData.theme.rootController.navigationBar.accentTextColor, for: .normal)
            button.titleLabel?.font = UIFont.boldSystemFont(ofSize: 15)
        } else {
            button.setTitleColor(presentationData.theme.rootController.navigationBar.secondaryTextColor, for: .normal)
            button.titleLabel?.font = UIFont.systemFont(ofSize: 15)
        }

        button.addTarget(
            AITranslationToggleTarget(action: action),
            action: #selector(AITranslationToggleTarget.tapped),
            for: .touchUpInside
        )

        return UIBarButtonItem(customView: button)
    }
}

/// Helper class to handle button tap via target-action pattern.
private final class AITranslationToggleTarget: NSObject {
    private let handler: () -> Void

    init(action: @escaping () -> Void) {
        self.handler = action
        super.init()
    }

    @objc func tapped() {
        handler()
    }
}
