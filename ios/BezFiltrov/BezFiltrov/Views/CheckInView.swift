import SwiftUI

/// PRD §11.8 — an unskippable but non-blocking check-in every few cards
/// at intensity 4+. Never phrased as a test; always an easy way out.
struct CheckInView: View {
    @EnvironmentObject var store: SessionStore

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "heart.text.square.fill")
                .font(.system(size: 44))
                .foregroundStyle(Theme.accentSecondary)

            Text("Всё ещё в комфорте?")
                .font(.title2.bold())
                .foregroundStyle(Theme.textPrimary)

            Text("Это не тест — просто короткая сверка. Отвечайте честно, это между вами.")
                .font(.subheadline)
                .foregroundStyle(Theme.textPrimary.opacity(0.7))
                .multilineTextAlignment(.center)

            VStack(spacing: 12) {
                Button {
                    store.dismissCheckIn()
                } label: {
                    Text("Да, продолжаем")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.signalSafe)

                Button {
                    store.returnToLevelSelect()
                } label: {
                    Text("Хочу сбавить темп")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.bordered)
                .tint(Theme.signalCaution)

                Button {
                    store.endSession()
                } label: {
                    Text("Хочу остановиться")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.bordered)
                .tint(Theme.signalStop)
            }
        }
        .padding(32)
    }
}
