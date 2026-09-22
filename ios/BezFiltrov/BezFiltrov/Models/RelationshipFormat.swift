import Foundation

/// Ready-made filters, never assumed: a session's format is chosen once,
/// by the players, in SessionSetupView — no card infers it from anything else.
enum RelationshipFormat: String, Codable, CaseIterable, Identifiable, Sendable {
    case any
    case oneOnOne
    case mf
    case mm
    case ff
    case mfm
    case fmf
    case mmm
    case fff
    case mixedGroup
    case openRelationship
    case swinging
    case polyamory

    var id: String { rawValue }

    var title: String {
        switch self {
        case .any: return "Любой формат"
        case .oneOnOne: return "Один на один"
        case .mf: return "МЖ"
        case .mm: return "ММ"
        case .ff: return "ЖЖ"
        case .mfm: return "МЖМ"
        case .fmf: return "ЖМЖ"
        case .mmm: return "МММ"
        case .fff: return "ЖЖЖ"
        case .mixedGroup: return "Смешанная группа"
        case .openRelationship: return "Открытые отношения"
        case .swinging: return "Свинг"
        case .polyamory: return "Полиамория"
        }
    }
}
