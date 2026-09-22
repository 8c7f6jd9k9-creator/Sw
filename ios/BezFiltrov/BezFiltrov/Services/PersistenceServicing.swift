import Foundation

enum PersistenceError: Error, LocalizedError {
    case decodingFailed(key: StorageKey, underlying: Error)
    case encodingFailed(key: StorageKey, underlying: Error)

    var errorDescription: String? {
        switch self {
        case .decodingFailed(let key, let underlying):
            return "Не удалось прочитать сохранённые данные (\(key.rawValue)): \(underlying.localizedDescription)"
        case .encodingFailed(let key, let underlying):
            return "Не удалось сохранить данные (\(key.rawValue)): \(underlying.localizedDescription)"
        }
    }
}

protocol PersistenceServicing: Sendable {
    func load<T: Decodable & Sendable>(_ type: T.Type, key: StorageKey) async throws -> T?
    func save<T: Encodable & Sendable>(_ value: T, key: StorageKey) async throws
}

/// An actor, not a singleton: every read/write is serialized, and every
/// failure is thrown rather than swallowed — a corrupted or incompatible
/// payload surfaces as `PersistenceError`, letting the caller fall back to
/// a default value deliberately instead of the app silently losing state.
actor PersistenceService: PersistenceServicing {
    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    func load<T: Decodable & Sendable>(_ type: T.Type, key: StorageKey) async throws -> T? {
        guard let data = defaults.data(forKey: key.rawValue) else { return nil }
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw PersistenceError.decodingFailed(key: key, underlying: error)
        }
    }

    func save<T: Encodable & Sendable>(_ value: T, key: StorageKey) async throws {
        do {
            let data = try JSONEncoder().encode(value)
            defaults.set(data, forKey: key.rawValue)
        } catch {
            throw PersistenceError.encodingFailed(key: key, underlying: error)
        }
    }
}
