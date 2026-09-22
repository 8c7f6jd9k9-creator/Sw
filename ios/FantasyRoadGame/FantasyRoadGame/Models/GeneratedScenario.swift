import Foundation

/// A randomly assembled "where — when — with whom — what for" scenario.
struct GeneratedScenario: Identifiable, Codable, Equatable {
    let id: UUID
    let levelID: Int
    let whereText: String
    let whenText: String
    let withWhomText: String
    let goalText: String

    init(
        id: UUID = UUID(),
        levelID: Int,
        whereText: String,
        whenText: String,
        withWhomText: String,
        goalText: String
    ) {
        self.id = id
        self.levelID = levelID
        self.whereText = whereText
        self.whenText = whenText
        self.withWhomText = withWhomText
        self.goalText = goalText
    }

    var sentence: String {
        "Где: \(whereText). Когда: \(whenText). С кем: \(withWhomText). Куда: \(goalText)."
    }
}
