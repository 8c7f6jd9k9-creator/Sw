import Foundation

/// The six game modes from the PRD. Only `.questions` ships in M1;
/// the rest are modeled now so content and session state don't need
/// breaking changes when they land.
enum GameMode: String, Codable, CaseIterable, Identifiable, Sendable {
    case questions
    case truthOrDare
    case matches
    case scenario
    case wheel
    case custom

    var id: String { rawValue }

    var title: String {
        switch self {
        case .questions: return "Откровенные вопросы"
        case .truthOrDare: return "Правда или действие"
        case .matches: return "Совпадения"
        case .scenario: return "Генератор сценариев"
        case .wheel: return "Колесо фантазий"
        case .custom: return "Своя колода"
        }
    }

    /// M1 ships one working mode; the rest are visible-but-disabled
    /// placeholders so the level/mode picker reflects the full roadmap.
    var isAvailableInM1: Bool {
        self == .questions
    }
}
