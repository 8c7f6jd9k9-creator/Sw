import Foundation

/// One per player per session. `revokedAt != nil` immediately blocks every
/// card whose `requiredConsent` overlaps this record's granted topics,
/// for the rest of the session, no explanation required.
struct ConsentRecord: Identifiable, Codable, Hashable, Sendable {
    let id: UUID
    let playerID: UUID
    var grantedTopics: Set<ConsentTopic>
    let grantedAt: Date
    var revokedAt: Date?

    init(
        id: UUID = UUID(),
        playerID: UUID,
        grantedTopics: Set<ConsentTopic>,
        grantedAt: Date = Date(),
        revokedAt: Date? = nil
    ) {
        self.id = id
        self.playerID = playerID
        self.grantedTopics = grantedTopics
        self.grantedAt = grantedAt
        self.revokedAt = revokedAt
    }

    var isActive: Bool { revokedAt == nil }

    func hasConsent(for topic: ConsentTopic) -> Bool {
        isActive && grantedTopics.contains(topic)
    }
}
