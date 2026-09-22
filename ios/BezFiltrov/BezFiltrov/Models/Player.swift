import Foundation

struct Player: Identifiable, Codable, Hashable, Sendable {
    let id: UUID
    var displayName: String
    var pronounPreference: String
    var ageConfirmed18: Bool
    var avatarColorHex: String

    init(
        id: UUID = UUID(),
        displayName: String,
        pronounPreference: String = "",
        ageConfirmed18: Bool = false,
        avatarColorHex: String = "A8577B"
    ) {
        self.id = id
        self.displayName = displayName
        self.pronounPreference = pronounPreference
        self.ageConfirmed18 = ageConfirmed18
        self.avatarColorHex = avatarColorHex
    }
}
