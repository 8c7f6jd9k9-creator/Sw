import Foundation

/// "Точно да / возможно / точно нет / обсудить позже" — a player's stance
/// on one `Topic`. `.no` from *any* player removes that topic's cards from
/// the shared deck for the whole session.
enum BoundaryLevel: String, Codable, CaseIterable, Identifiable, Sendable {
    case yes
    case maybe
    case no
    case discussLater

    var id: String { rawValue }

    var title: String {
        switch self {
        case .yes: return "Точно да"
        case .maybe: return "Возможно"
        case .no: return "Точно нет"
        case .discussLater: return "Обсудить позже"
        }
    }
}
