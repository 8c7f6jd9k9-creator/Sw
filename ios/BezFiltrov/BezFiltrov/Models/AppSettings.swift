import SwiftUI

enum AppAppearance: String, Codable, CaseIterable, Identifiable, Hashable, Sendable {
    case system
    case light
    case dark

    var id: String { rawValue }

    var title: String {
        switch self {
        case .system: return "Как в системе"
        case .light: return "Светлая"
        case .dark: return "Тёмная"
        }
    }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
}

struct AppSettings: Codable, Equatable, Sendable {
    var analyticsEnabled: Bool
    var sessionHistoryStoresAnswers: Bool
    var appearance: AppAppearance
    var reduceMotionOverride: Bool
    var hapticsEnabled: Bool

    static let `default` = AppSettings(
        analyticsEnabled: false,
        sessionHistoryStoresAnswers: false,
        appearance: .system,
        reduceMotionOverride: false,
        hapticsEnabled: true
    )
}
