import Foundation
import Combine

/// Central observable state: decks, favorites, settings, stats and persistence.
final class GameStore: ObservableObject {

    @Published var settings: GameSettings
    @Published var stats: GameStats
    @Published var favoriteIDs: Set<String>
    @Published var customCards: [GameCard]
    @Published var savedScenarios: [GeneratedScenario]
    @Published var hasOnboarded: Bool

    @Published var selectedLevelID: Int
    @Published private(set) var currentCard: GameCard?
    @Published private(set) var roundNumber: Int = 1
    @Published private(set) var cardsSeenInRound: Int = 0
    @Published var isPlayerOneTurn: Bool = true

    private var deck: [GameCard] = []
    private var lastScenario: GeneratedScenario?
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
        self.savedScenarios = GameStore.load([GeneratedScenario].self, key: .savedScenarios) ?? []
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
        lastScenario = nil
        buildDeck()
        drawNextCard()
        HapticsManager.shared.selection()
    }

    /// Jumps to a random level other than the current one (excludes the custom deck).
    func selectRandomLevel() {
        let candidates = (1...6).filter { $0 != selectedLevelID }
        guard let randomID = candidates.randomElement() else { return }
        selectLevel(randomID)
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
        savedScenarios.removeAll()
        save(savedScenarios, key: .savedScenarios)
    }

    // MARK: Scenario builder ("Где — Когда — С кем — Куда")

    /// Random scenario for the current level. Only defined for levels 1-5;
    /// returns nil for the custom deck (0) and the boundaries-discussion level (6).
    func generateScenario() -> GeneratedScenario? {
        guard let bank = ScenarioContent.bank(for: selectedLevelID) else { return nil }
        let scenario = GeneratedScenario(
            levelID: selectedLevelID,
            whereText: randomPick(from: bank.wheres, avoiding: lastScenario?.whereText),
            whenText: randomPick(from: bank.whens, avoiding: lastScenario?.whenText),
            withWhomText: randomPick(from: bank.withWhoms, avoiding: lastScenario?.withWhomText),
            goalText: randomPick(from: bank.goals, avoiding: lastScenario?.goalText)
        )
        lastScenario = scenario
        HapticsManager.shared.selection()
        return scenario
    }

    /// Picks a random element, avoiding an immediate repeat of the previous value when possible.
    private func randomPick(from pool: [String], avoiding previous: String?) -> String {
        guard pool.count > 1, let previous else {
            return pool.randomElement() ?? ""
        }
        let candidates = pool.filter { $0 != previous }
        return candidates.randomElement() ?? pool.randomElement() ?? ""
    }

    func saveScenario(_ scenario: GeneratedScenario) {
        guard !savedScenarios.contains(where: { $0.id == scenario.id }) else { return }
        savedScenarios.append(scenario)
        save(savedScenarios, key: .savedScenarios)
        HapticsManager.shared.success()
    }

    func removeScenario(_ scenario: GeneratedScenario) {
        savedScenarios.removeAll { $0.id == scenario.id }
        save(savedScenarios, key: .savedScenarios)
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
