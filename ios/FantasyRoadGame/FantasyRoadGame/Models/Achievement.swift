import Foundation

/// A milestone computed live from GameStore's persisted stats — nothing extra
/// to persist, "unlocked" is just a predicate over existing state.
struct Achievement: Identifiable {
    let id: String
    let title: String
    let subtitle: String
    let icon: String
    let isUnlocked: (GameStore) -> Bool
}
