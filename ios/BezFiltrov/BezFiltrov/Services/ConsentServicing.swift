import Foundation

/// The single entry point every mode must call before showing a card or a
/// scenario step (PRD §11). No Store re-implements this check.
protocol ConsentServicing {
    func canReveal(
        _ card: Card,
        for playerIDs: [UUID],
        consentRecords: [UUID: ConsentRecord],
        boundaryProfiles: [UUID: BoundaryProfile]
    ) -> Bool
}

struct ConsentService: ConsentServicing {

    func canReveal(
        _ card: Card,
        for playerIDs: [UUID],
        consentRecords: [UUID: ConsentRecord],
        boundaryProfiles: [UUID: BoundaryProfile]
    ) -> Bool {
        for topic in card.requiredConsent {
            for playerID in playerIDs {
                guard let record = consentRecords[playerID], record.hasConsent(for: topic) else {
                    return false
                }
            }
        }

        for topic in card.topics {
            for playerID in playerIDs {
                if boundaryProfiles[playerID]?.level(for: topic) == .no {
                    return false
                }
            }
        }

        return true
    }
}
