import SwiftUI

/// Always in the same spot on screen, always ≥44×44pt, never dimmed by
/// `accentGlow` even at the hottest levels — see design system §7.
struct PauseOverlay: View {
    @EnvironmentObject var store: SessionStore
    @State private var showStopConfirmation = false
    @State private var showConsentReview = false

    var body: some View {
        HStack(spacing: 10) {
            if store.isPaused {
                Button {
                    store.resume()
                } label: {
                    Label("Продолжить", systemImage: "play.fill")
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.signalSafe)

                Button {
                    showConsentReview = true
                } label: {
                    Label("Согласие", systemImage: "checkmark.shield")
                }
                .buttonStyle(.bordered)
                .tint(Theme.accentSecondary)
            } else {
                Button {
                    store.pause()
                } label: {
                    Label("Пауза", systemImage: "pause.fill")
                }
                .buttonStyle(.bordered)
                .tint(Theme.signalCaution)
            }

            Button {
                showStopConfirmation = true
            } label: {
                Label("Завершить", systemImage: "stop.fill")
            }
            .buttonStyle(.bordered)
            .tint(Theme.signalStop)
        }
        .controlSize(.large)
        .padding(16)
        .confirmationDialog(
            "Завершить игру?",
            isPresented: $showStopConfirmation,
            titleVisibility: .visible
        ) {
            Button("Завершить и перейти к итогам", role: .destructive) {
                store.endSession()
            }
            Button("Отмена", role: .cancel) {}
        } message: {
            Text("Вы перейдёте к короткому разговору о том, как прошёл вечер.")
        }
        .sheet(isPresented: $showConsentReview) {
            ConsentReviewView()
        }
    }
}
