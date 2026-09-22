import Foundation

enum AnswerFormat: String, Codable, Sendable {
    case yesNoMaybe
    case singleChoice
    case openText
    case privateAnswer
    case simultaneousReveal
    case matchCheck
    case discussAfter
    case addOwnOption
}
