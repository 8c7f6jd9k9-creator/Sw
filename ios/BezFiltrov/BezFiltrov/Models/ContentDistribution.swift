import Foundation

/// Every App Store build card is `.appStoreSafe`. `.adultOnly` cards exist
/// only in the (unshipped, v1.1+) web/PWA content catalog and must never
/// be compiled into this target.
enum ContentDistribution: String, Codable, Sendable {
    case appStoreSafe
    case adultOnly
}
