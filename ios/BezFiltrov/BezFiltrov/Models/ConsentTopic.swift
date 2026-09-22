import Foundation

/// The three separately-grantable consents from the PRD (§11). A card whose
/// `requiredConsent` includes one of these is withheld until *every*
/// participating player has that specific consent active.
enum ConsentTopic: String, Codable, CaseIterable, Identifiable, Sendable {
    case physicalContact
    case thirdPartyParticipation
    case recording

    var id: String { rawValue }

    var title: String {
        switch self {
        case .physicalContact: return "Физический контакт"
        case .thirdPartyParticipation: return "Участие третьих лиц"
        case .recording: return "Фото, видео или аудио"
        }
    }
}
