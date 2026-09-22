import SwiftUI

struct RootView: View {
    @EnvironmentObject var store: GameStore

    var body: some View {
        Group {
            if store.hasOnboarded {
                MainTabView()
            } else {
                OnboardingView()
            }
        }
        .preferredColorScheme(store.settings.appearance.colorScheme)
    }
}

struct MainTabView: View {
    var body: some View {
        TabView {
            GameView()
                .tabItem {
                    Label("Игра", systemImage: "sparkles")
                }

            FavoritesView()
                .tabItem {
                    Label("Копилка", systemImage: "heart.fill")
                }

            SettingsView()
                .tabItem {
                    Label("Настройки", systemImage: "gearshape.fill")
                }
        }
    }
}
