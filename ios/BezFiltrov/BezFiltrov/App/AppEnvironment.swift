import Foundation

/// Assembled once in `BezFiltrovApp.init()` and handed to `SessionStore`
/// through its initializer — dependency injection instead of `.shared`
/// singletons, so every service can be swapped for a test fake.
struct AppEnvironment {
    let persistence: PersistenceServicing
    let consentService: ConsentServicing
    let deckService: DeckServicing
    let haptics: HapticsProviding

    static func live() -> AppEnvironment {
        let consentService = ConsentService()
        return AppEnvironment(
            persistence: PersistenceService(),
            consentService: consentService,
            deckService: DeckService(consentService: consentService),
            haptics: HapticsManager()
        )
    }
}
