import SwiftUI

enum AppAppearance: String, Codable, CaseIterable, Identifiable, Hashable {
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

struct GameSettings: Codable, Equatable {
    var playerOneName: String
    var playerTwoName: String
    var coupleModeEnabled: Bool
    var hapticsEnabled: Bool
    var appearance: AppAppearance

    static let `default` = GameSettings(
        playerOneName: "Игрок 1",
        playerTwoName: "Игрок 2",
        coupleModeEnabled: false,
        hapticsEnabled: true,
        appearance: .system
    )
}
