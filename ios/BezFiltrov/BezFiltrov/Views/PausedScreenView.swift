import SwiftUI

/// What screen 7 becomes on Pause — the current card is hidden entirely,
/// not just dimmed, per PRD §11.4.
struct PausedScreenView: View {
    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "pause.circle.fill")
                .font(.system(size: 56))
                .foregroundStyle(Theme.accentSecondary)
            Text("Игра на паузе")
                .font(.title.bold())
                .foregroundStyle(Theme.textPrimary)
            Text("Карточка скрыта. Нажмите «Продолжить», когда будете готовы.")
                .font(.subheadline)
                .foregroundStyle(Theme.textPrimary.opacity(0.6))
                .multilineTextAlignment(.center)
        }
        .padding(40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
