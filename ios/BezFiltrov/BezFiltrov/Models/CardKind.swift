import Foundation

enum CardKind: String, Codable, Sendable {
    case question
    /// Phrased as an invitation ("если оба согласны, предложите…"), never a command.
    case dare
}
