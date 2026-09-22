import Foundation

struct GameStats: Codable, Equatable {
    var totalCardsPlayed: Int = 0
    var perLevelPlayed: [Int: Int] = [:]
}
