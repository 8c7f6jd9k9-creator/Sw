import Foundation

protocol DeckServicing {
    func buildDeck(
        from allCards: [Card],
        intensityLevel: Int,
        playerIDs: [UUID],
        consentRecords: [UUID: ConsentRecord],
        boundaryProfiles: [UUID: BoundaryProfile]
    ) -> [Card]
}

struct DeckService: DeckServicing {
    let consentService: ConsentServicing

    func buildDeck(
        from allCards: [Card],
        intensityLevel: Int,
        playerIDs: [UUID],
        consentRecords: [UUID: ConsentRecord],
        boundaryProfiles: [UUID: BoundaryProfile]
    ) -> [Card] {
        allCards
            .filter { $0.intensityLevel == intensityLevel }
            .filter {
                consentService.canReveal(
                    $0,
                    for: playerIDs,
                    consentRecords: consentRecords,
                    boundaryProfiles: boundaryProfiles
                )
            }
            .shuffled()
    }
}
