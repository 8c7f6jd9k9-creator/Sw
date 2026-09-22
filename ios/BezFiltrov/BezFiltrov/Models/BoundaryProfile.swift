import Foundation

/// One player's stance on one `Topic`. Missing entries are treated as
/// `.discussLater`, never as implicit `.yes` — see `DeckServicing`.
struct BoundaryEntry: Identifiable, Codable, Hashable, Sendable {
    var id: Topic { topic }
    let topic: Topic
    var level: BoundaryLevel
    var updatedAt: Date
}

struct BoundaryProfile: Codable, Hashable, Sendable {
    let playerID: UUID
    var entries: [Topic: BoundaryEntry]

    init(playerID: UUID, entries: [Topic: BoundaryEntry] = [:]) {
        self.playerID = playerID
        self.entries = entries
    }

    func level(for topic: Topic) -> BoundaryLevel {
        entries[topic]?.level ?? .discussLater
    }

    mutating func setLevel(_ level: BoundaryLevel, for topic: Topic) {
        entries[topic] = BoundaryEntry(topic: topic, level: level, updatedAt: Date())
    }
}
