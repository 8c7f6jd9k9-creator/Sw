import SwiftUI

struct RootView: View {
    @EnvironmentObject var store: SessionStore

    var body: some View {
        ZStack {
            Theme.backgroundPrimary.ignoresSafeArea()

            Group {
                switch store.screen {
                case .welcome:
                    WelcomeView()
                case .setup:
                    SessionSetupView()
                case .addPlayers:
                    AddPlayersView()
                case .consent:
                    ConsentFlowView()
                case .levelSelect:
                    LevelSelectView()
                case .playing:
                    ZStack {
                        if store.isPaused {
                            PausedScreenView()
                        } else {
                            GameScreenView()
                        }
                    }
                    .overlay(alignment: .topTrailing) {
                        PauseOverlay()
                    }
                case .aftercare:
                    AftercareFlowView()
                case .done:
                    SessionDoneView()
                }
            }
            .transition(.opacity)
        }
        .animation(.easeInOut(duration: 0.25), value: store.screen)
        .alert(
            "Что-то пошло не так",
            isPresented: Binding(
                get: { store.lastErrorMessage != nil },
                set: { if !$0 { store.lastErrorMessage = nil } }
            )
        ) {
            Button("Понятно", role: .cancel) { store.lastErrorMessage = nil }
        } message: {
            Text(store.lastErrorMessage ?? "")
        }
    }
}
