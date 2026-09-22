import UIKit

/// Behind a protocol so stores can be unit-tested with a no-op fake instead
/// of touching UIKit's feedback generators.
protocol HapticsProviding: AnyObject {
    var isEnabled: Bool { get set }
    func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle)
    func success()
    func selection()
}

/// Constructed once in `AppEnvironment` and passed by reference — not a
/// global singleton, even though a class instance is naturally shared.
final class HapticsManager: HapticsProviding {
    var isEnabled: Bool = true

    func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle = .medium) {
        guard isEnabled else { return }
        UIImpactFeedbackGenerator(style: style).impactOccurred()
    }

    func success() {
        guard isEnabled else { return }
        UINotificationFeedbackGenerator().notificationOccurred(.success)
    }

    func selection() {
        guard isEnabled else { return }
        UISelectionFeedbackGenerator().selectionChanged()
    }
}
