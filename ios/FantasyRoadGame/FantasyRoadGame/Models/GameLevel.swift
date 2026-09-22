import Foundation

/// A themed deck of cards with an escalating intensity level.
struct GameLevel: Identifiable, Hashable {
    let id: Int
    let title: String
    let emoji: String
    let subtitle: String
    let cards: [GameCard]
}
