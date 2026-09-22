import Foundation

/// Filtering tags only — never used to phrase card text, which always
/// stays a question/invitation about desire, consent or boundaries.
enum Topic: String, Codable, CaseIterable, Identifiable, Sendable {
    case desires
    case intimacyStyles
    case fantasy
    case roleplay
    case toys
    case oral
    case anal
    case strapOn
    case bisexualCuriosity
    case multiplePartners
    case swinging
    case openRelationships
    case jealousy
    case voyeurismExhibitionism
    case dominanceSubmission
    case lightBDSM
    case costumesPersona
    case sexAwayFromHome
    case roleplayScenarios
    case boundariesAndSafewords

    var id: String { rawValue }

    var title: String {
        switch self {
        case .desires: return "Желания и предпочтения"
        case .intimacyStyles: return "Формы близости"
        case .fantasy: return "Фантазии"
        case .roleplay: return "Ролевые игры"
        case .toys: return "Игрушки"
        case .oral: return "Оральные практики"
        case .anal: return "Анальные практики"
        case .strapOn: return "Страпон"
        case .bisexualCuriosity: return "Бисексуальный интерес"
        case .multiplePartners: return "Несколько партнёров"
        case .swinging: return "Свинг"
        case .openRelationships: return "Открытые отношения"
        case .jealousy: return "Ревность"
        case .voyeurismExhibitionism: return "Наблюдение и демонстрация"
        case .dominanceSubmission: return "Доминирование и подчинение"
        case .lightBDSM: return "Мягкий BDSM"
        case .costumesPersona: return "Костюмы и перевоплощение"
        case .sexAwayFromHome: return "Секс вне дома"
        case .roleplayScenarios: return "Ролевые сценарии"
        case .boundariesAndSafewords: return "Границы и стоп-слова"
        }
    }
}
