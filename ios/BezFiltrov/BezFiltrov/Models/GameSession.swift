import Foundation

enum SessionKind: String, Codable, Sendable {
    case pair
    case group
}

enum DeviceMode: String, Codable, Sendable {
    case singleShared
    case passDevice
}

enum SessionStatus: String, Codable, Sendable {
    case active
    case paused
    case ended
}

struct GameSession: Identifiable, Codable, Hashable, Sendable {
    let id: UUID
    var createdAt: Date
    var sessionKind: SessionKind
    var deviceMode: DeviceMode
    var relationshipFormat: RelationshipFormat
    var playerIDs: [UUID]
    var selectedMode: GameMode
    var intensityLevel: Int
    var status: SessionStatus

    init(
        id: UUID = UUID(),
        createdAt: Date = Date(),
        sessionKind: SessionKind,
        deviceMode: DeviceMode,
        relationshipFormat: RelationshipFormat = .any,
        playerIDs: [UUID] = [],
        selectedMode: GameMode = .questions,
        intensityLevel: Int = 1,
        status: SessionStatus = .active
    ) {
        self.id = id
        self.createdAt = createdAt
        self.sessionKind = sessionKind
        self.deviceMode = deviceMode
        self.relationshipFormat = relationshipFormat
        self.playerIDs = playerIDs
        self.selectedMode = selectedMode
        self.intensityLevel = intensityLevel
        self.status = status
    }
}
