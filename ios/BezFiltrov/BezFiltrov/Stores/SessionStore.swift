import Foundation

/// Orchestrates the M1 flow: onboarding → consent → level → play → aftercare.
/// UI state only lives here as far as *which screen* is showing; card-flip
/// animation state stays in the view. All domain logic (consent, deck
/// building) is delegated to the injected services — this store wires them
/// together and owns persistence, it doesn't reimplement either.
@MainActor
final class SessionStore: ObservableObject {

    enum Screen: Equatable {
        case welcome
        case setup
        case addPlayers
        case consent
        case levelSelect
        case playing
        case aftercare
        case done
    }

    @Published private(set) var screen: Screen = .welcome
    @Published var settings: AppSettings = .default
    @Published private(set) var players: [Player] = []
    @Published private(set) var consentRecords: [UUID: ConsentRecord] = [:]
    @Published private(set) var boundaryProfiles: [UUID: BoundaryProfile] = [:]
    @Published private(set) var session: GameSession?
    @Published private(set) var currentCard: Card?
    @Published private(set) var roundNumber: Int = 1
    @Published private(set) var cardsSeenInRound: Int = 0
    @Published private(set) var totalCardsInRound: Int = 0
    @Published var isPaused: Bool = false
    @Published private(set) var aftercareNotes: [UUID: AftercareNote] = [:]
    @Published var lastErrorMessage: String?
    @Published private(set) var showCheckIn: Bool = false

    private let environment: AppEnvironment
    private var deck: [Card] = []
    private var advanceTask: Task<Void, Never>?
    private var hotCardsSinceCheckIn: Int = 0
    private let checkInThreshold = 4
    private let checkInLevel = 4

    var availableTopics: [Topic] {
        let used = Set(ContentCatalog.questions.flatMap { $0.topics })
        return Topic.allCases.filter { used.contains($0) }
    }

    init(environment: AppEnvironment) {
        self.environment = environment
        Task { await loadPersistedSettings() }
    }

    private func loadPersistedSettings() async {
        do {
            if let loaded = try await environment.persistence.load(AppSettings.self, key: .settings) {
                settings = loaded
            }
        } catch {
            lastErrorMessage = (error as? LocalizedError)?.errorDescription ?? "Не удалось загрузить настройки."
            settings = .default
        }
        environment.haptics.isEnabled = settings.hapticsEnabled
    }

    func persistSettings() {
        environment.haptics.isEnabled = settings.hapticsEnabled
        let toSave = settings
        Task {
            do {
                try await environment.persistence.save(toSave, key: .settings)
            } catch {
                lastErrorMessage = (error as? LocalizedError)?.errorDescription ?? "Не удалось сохранить настройки."
            }
        }
    }

    // MARK: Onboarding

    func confirmAgeGate() {
        screen = .setup
    }

    func startSetup(kind: SessionKind, deviceMode: DeviceMode, relationshipFormat: RelationshipFormat) {
        session = GameSession(sessionKind: kind, deviceMode: deviceMode, relationshipFormat: relationshipFormat)
        screen = .addPlayers
    }

    // MARK: Players

    func addPlayer(name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let colors = ["A8577B", "C9915B", "6FA98C", "8E9AAF"]
        let player = Player(displayName: trimmed, avatarColorHex: colors[players.count % colors.count])
        players.append(player)
        session?.playerIDs.append(player.id)
    }

    func removePlayer(_ player: Player) {
        players.removeAll { $0.id == player.id }
        session?.playerIDs.removeAll { $0 == player.id }
        consentRecords[player.id] = nil
        boundaryProfiles[player.id] = nil
    }

    func finishAddingPlayers() {
        guard players.count >= 2 else { return }
        screen = .consent
    }

    // MARK: Consent

    func recordConsent(
        playerID: UUID,
        ageConfirmed: Bool,
        grantedTopics: Set<ConsentTopic>,
        boundaries: [Topic: BoundaryLevel]
    ) {
        guard ageConfirmed else { return }

        consentRecords[playerID] = ConsentRecord(playerID: playerID, grantedTopics: grantedTopics)

        var profile = BoundaryProfile(playerID: playerID)
        for (topic, level) in boundaries {
            profile.setLevel(level, for: topic)
        }
        boundaryProfiles[playerID] = profile

        if let index = players.firstIndex(where: { $0.id == playerID }) {
            players[index].ageConfirmed18 = true
        }
    }

    var allPlayersHaveConsented: Bool {
        !players.isEmpty && players.allSatisfy { consentRecords[$0.id]?.isActive == true }
    }

    func finishConsent() {
        guard allPlayersHaveConsented else { return }
        screen = .levelSelect
    }

    /// Symmetric with `revokeConsent` — granting mid-session is always allowed,
    /// it just can't retroactively un-withhold a card the deck already skipped.
    func grantConsent(playerID: UUID, topic: ConsentTopic) {
        consentRecords[playerID]?.grantedTopics.insert(topic)
    }

    /// Revoking is immediate and total for the rest of the session — see PRD §11.4/§11.7.
    func revokeConsent(playerID: UUID, topic: ConsentTopic) {
        consentRecords[playerID]?.grantedTopics.remove(topic)
        guard let session else { return }

        deck = deck.filter {
            environment.consentService.canReveal(
                $0,
                for: session.playerIDs,
                consentRecords: consentRecords,
                boundaryProfiles: boundaryProfiles
            )
        }

        if let current = currentCard,
           !environment.consentService.canReveal(
               current,
               for: session.playerIDs,
               consentRecords: consentRecords,
               boundaryProfiles: boundaryProfiles
           ) {
            commitAdvance()
        }
    }

    // MARK: Level & deck

    func selectLevel(_ level: Int) {
        guard var updatedSession = session else { return }
        updatedSession.intensityLevel = level
        session = updatedSession
        roundNumber = 1
        hotCardsSinceCheckIn = 0
        buildDeck()
        screen = .playing
        commitAdvance()
    }

    private func buildDeck() {
        guard let session else { return }
        let fresh = environment.deckService.buildDeck(
            from: ContentCatalog.questions,
            intensityLevel: session.intensityLevel,
            playerIDs: session.playerIDs,
            consentRecords: consentRecords,
            boundaryProfiles: boundaryProfiles
        )
        deck = fresh
        totalCardsInRound = fresh.count
        cardsSeenInRound = 0
    }

    /// Debounced by a cancellable `Task`: a second call before the first
    /// settles cancels it, so rapid taps advance the deck at most once and
    /// never double-count a card as played.
    func requestAdvance() {
        advanceTask?.cancel()
        advanceTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 120_000_000)
            guard let self, !Task.isCancelled else { return }
            self.commitAdvance()
        }
    }

    private func commitAdvance() {
        guard let session, !ContentCatalog.questions.isEmpty else {
            currentCard = nil
            return
        }

        if deck.isEmpty {
            roundNumber += 1
            buildDeck()
        }

        guard !deck.isEmpty else {
            currentCard = nil
            return
        }

        currentCard = deck.removeFirst()
        cardsSeenInRound += 1
        environment.haptics.impact(.light)

        if session.intensityLevel >= checkInLevel {
            hotCardsSinceCheckIn += 1
            if hotCardsSinceCheckIn >= checkInThreshold {
                hotCardsSinceCheckIn = 0
                showCheckIn = true
            }
        }
    }

    func dismissCheckIn() {
        showCheckIn = false
    }

    /// "Хочу сбавить темп" from the check-in — back to level select, current
    /// deck discarded, nothing about this counts as ending the session.
    func returnToLevelSelect() {
        advanceTask?.cancel()
        showCheckIn = false
        hotCardsSinceCheckIn = 0
        currentCard = nil
        deck = []
        screen = .levelSelect
    }

    // MARK: Pause / Stop

    func pause() {
        advanceTask?.cancel()
        isPaused = true
    }

    func resume() {
        isPaused = false
    }

    func endSession() {
        advanceTask?.cancel()
        isPaused = false
        session?.status = .ended
        screen = .aftercare
    }

    // MARK: Aftercare

    func recordAftercare(playerID: UUID, feeling: String, whatWorked: String, whatToAvoid: String) {
        guard let session else { return }
        var note = aftercareNotes[playerID] ?? AftercareNote(sessionID: session.id, playerID: playerID)
        note.feeling = feeling
        note.whatWorked = whatWorked
        note.whatToAvoid = whatToAvoid
        note.completedAt = Date()
        aftercareNotes[playerID] = note
    }

    var allPlayersCompletedAftercare: Bool {
        !players.isEmpty && players.allSatisfy { aftercareNotes[$0.id]?.completedAt != nil }
    }

    func finishAftercare() {
        guard allPlayersCompletedAftercare else { return }
        screen = .done
    }

    func startNewSession() {
        advanceTask?.cancel()
        session = nil
        players = []
        consentRecords = [:]
        boundaryProfiles = [:]
        currentCard = nil
        deck = []
        aftercareNotes = [:]
        roundNumber = 1
        cardsSeenInRound = 0
        totalCardsInRound = 0
        hotCardsSinceCheckIn = 0
        showCheckIn = false
        isPaused = false
        screen = .welcome
    }
}
