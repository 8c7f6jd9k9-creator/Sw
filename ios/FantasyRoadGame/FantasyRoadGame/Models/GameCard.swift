import Foundation

/// A single prompt shown to the players.
struct GameCard: Identifiable, Hashable, Codable {

    enum Kind: String, Codable, Hashable {
        case question
        case dare
    }

    /// Stable, human-readable identifier used for persistence (favorites, stats).
    /// Unlike `UUID()`, this survives app relaunches and code changes to unrelated cards.
    let id: String
    let levelID: Int
    let category: String
    let text: String
    let kind: Kind

    init(id: String, levelID: Int, category: String, text: String, kind: Kind = .question) {
        self.id = id
        self.levelID = levelID
        self.category = category
        self.text = text
        self.kind = kind
    }
}
