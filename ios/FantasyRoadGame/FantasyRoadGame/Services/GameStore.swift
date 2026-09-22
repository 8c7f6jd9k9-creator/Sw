import Foundation
import Combine

/// Central observable state: decks, favorites, settings, stats and persistence.
final class GameStore: ObservableObject {

    @Published var settings: GameSettings
    @Published var stats: GameStats
    @Published var favoriteIDs: Set<String>
    @Published var customCards: [GameCard]
    @Published var hasOnboarded: Bool

    @Published var selectedLevelID: Int
    @Published private(set) var currentCard: GameCard?
    @Published private(set) var roundNumber: Int = 1
    @Published private(set) var cardsSeenInRound: Int = 0
    @Published var isPlayerOneTurn: Bool = true

    private var deck: [GameCard] = []
    private let defaults = UserDefaults.standard

    var levels: [GameLevel] {
        let customLevel = GameLevel(
            id: 0,
            title: "Свои карточки",
            emoji: "✏️",
            subtitle: "Добавлены вами в настройках",
            cards: customCards
        )
        return [customLevel] + GameContent.levels
    }

    var currentLevel: GameLevel {
        levels.first(where: { $0.id == selectedLevelID }) ?? levels[2]
    }

    var totalCardsInLevel: Int {
        currentLevel.cards.count
    }

    init() {
        let loadedSettings = GameStore.load(GameSettings.self, key: .settings) ?? .default
        self.settings = loadedSettings
        self.stats = GameStore.load(GameStats.self, key: .stats) ?? GameStats()
        self.favoriteIDs = Set(GameStore.load([String].self, key: .favorites) ?? [])
        self.customCards = GameStore.load([GameCard].self, key: .customCards) ?? []
        self.hasOnboarded = UserDefaults.standard.bool(forKey: StorageKey.hasOnboarded.rawValue)

        if UserDefaults.standard.object(forKey: StorageKey.selectedLevelID.rawValue) != nil {
            self.selectedLevelID = UserDefaults.standard.integer(forKey: StorageKey.selectedLevelID.rawValue)
        } else {
            self.selectedLevelID = 2
        }

        HapticsManager.shared.isEnabled = loadedSettings.hapticsEnabled

        buildDeck()
        drawNextCard()
    }

    // MARK: Persistence helpers

    private static func load<T: Decodable>(_ type: T.Type, key: StorageKey) -> T? {
        guard let data = UserDefaults.standard.data(forKey: key.rawValue) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    private func save<T: Encodable>(_ value: T, key: StorageKey) {
        guard let data = try? JSONEncoder().encode(value) else { return }
        defaults.set(data, forKey: key.rawValue)
    }

    // MARK: Onboarding & settings

    func completeOnboarding(playerOne: String, playerTwo: String, coupleMode: Bool) {
        var updated = settings
        let trimmedOne = playerOne.trimmingCharacters(in: .whitespaces)
        let trimmedTwo = playerTwo.trimmingCharacters(in: .whitespaces)
        if !trimmedOne.isEmpty { updated.playerOneName = trimmedOne }
        if !trimmedTwo.isEmpty { updated.playerTwoName = trimmedTwo }
        updated.coupleModeEnabled = coupleMode
        settings = updated
        hasOnboarded = true
        defaults.set(true, forKey: StorageKey.hasOnboarded.rawValue)
        persistSettings()
    }

    func persistSettings() {
        save(settings, key: .settings)
        HapticsManager.shared.isEnabled = settings.hapticsEnabled
    }

    // MARK: Level & deck

    func selectLevel(_ id: Int) {
        guard id != selectedLevelID else { return }
        selectedLevelID = id
        defaults.set(id, forKey: StorageKey.selectedLevelID.rawValue)
        roundNumber = 1
        buildDeck()
        drawNextCard()
        HapticsManager.shared.selection()
    }

    private func buildDeck() {
        deck = currentLevel.cards.shuffled()
        cardsSeenInRound = 0
    }

    func drawNextCard() {
        guard !currentLevel.cards.isEmpty else {
            currentCard = nil
            return
        }

        if deck.isEmpty {
            roundNumber += 1
            buildDeck()
        }

        if settings.coupleModeEnabled && currentCard != nil {
            isPlayerOneTurn.toggle()
        }

        currentCard = deck.removeFirst()
        cardsSeenInRound += 1

        stats.totalCardsPlayed += 1
        stats.perLevelPlayed[selectedLevelID, default: 0] += 1
        save(stats, key: .stats)

        HapticsManager.shared.impact(.light)
    }

    // MARK: Favorites

    func toggleFavorite(_ card: GameCard) {
        if favoriteIDs.contains(card.id) {
            favoriteIDs.remove(card.id)
        } else {
            favoriteIDs.insert(card.id)
            HapticsManager.shared.success()
        }
        save(Array(favoriteIDs), key: .favorites)
    }

    func isFavorite(_ card: GameCard) -> Bool {
        favoriteIDs.contains(card.id)
    }

    var favoriteCards: [GameCard] {
        levels.flatMap { $0.cards }.filter { favoriteIDs.contains($0.id) }
    }

    func removeFavorite(_ card: GameCard) {
        favoriteIDs.remove(card.id)
        save(Array(favoriteIDs), key: .favorites)
    }

    func resetFavorites() {
        favoriteIDs.removeAll()
        save(Array(favoriteIDs), key: .favorites)
    }

    // MARK: Custom cards

    func addCustomCard(text: String, category: String) {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return }
        let trimmedCategory = category.trimmingCharacters(in: .whitespacesAndNewlines)

        let card = GameCard(
            id: "custom_\(UUID().uuidString)",
            levelID: 0,
            category: trimmedCategory.isEmpty ? "Своё" : trimmedCategory,
            text: trimmedText
        )
        customCards.append(card)
        save(customCards, key: .customCards)

        if selectedLevelID == 0 {
            buildDeck()
            if currentCard == nil {
                drawNextCard()
            }
        }
    }

    func removeCustomCard(_ card: GameCard) {
        customCards.removeAll { $0.id == card.id }
        save(customCards, key: .customCards)
        favoriteIDs.remove(card.id)
        save(Array(favoriteIDs), key: .favorites)

        if selectedLevelID == 0 {
            if currentCard?.id == card.id {
                currentCard = nil
            }
            buildDeck()
            if currentCard == nil {
                drawNextCard()
            }
        }
    }

    // MARK: Reset

    func resetProgress() {
        stats = GameStats()
        save(stats, key: .stats)
        roundNumber = 1
        buildDeck()
        drawNextCard()
    }
}
