import Foundation

/// Per-player aftercare answers for one session, shown to no one else.
struct AftercareNote: Identifiable, Codable, Hashable, Sendable {
    let id: UUID
    let sessionID: UUID
    let playerID: UUID
    var feeling: String
    var whatWorked: String
    var whatToAvoid: String
    var completedAt: Date?

    init(
        id: UUID = UUID(),
        sessionID: UUID,
        playerID: UUID,
        feeling: String = "",
        whatWorked: String = "",
        whatToAvoid: String = "",
        completedAt: Date? = nil
    ) {
        self.id = id
        self.sessionID = sessionID
        self.playerID = playerID
        self.feeling = feeling
        self.whatWorked = whatWorked
        self.whatToAvoid = whatToAvoid
        self.completedAt = completedAt
    }
}
