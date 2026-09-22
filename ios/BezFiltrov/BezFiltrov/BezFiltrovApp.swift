import SwiftUI

@main
struct BezFiltrovApp: App {
    @StateObject private var store: SessionStore

    init() {
        _store = StateObject(wrappedValue: SessionStore(environment: .live()))
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .preferredColorScheme(store.settings.appearance.colorScheme)
        }
    }
}
