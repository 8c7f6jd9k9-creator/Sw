import Foundation

/// A single prompt. `text` is always phrased as a question, desire or
/// invitation — never a graphic description or an instruction to act;
/// `topics` names what the card is *about* for filtering purposes only.
struct Card: Identifiable, Hashable, Codable, Sendable {
    let id: String
    let mode: GameMode
    let kind: CardKind
    let text: String
    let intensityLevel: Int
    let topics: [Topic]
    let playerCountRange: ClosedRange<Int>
    let relationshipFormats: [RelationshipFormat]
    let requiredConsent: [ConsentTopic]
    let sensitiveTriggers: [String]
    let answerFormat: AnswerFormat
    let distribution: ContentDistribution
    let contentVersion: Int
    let locale: String
    let lastReviewedAt: Date
}
