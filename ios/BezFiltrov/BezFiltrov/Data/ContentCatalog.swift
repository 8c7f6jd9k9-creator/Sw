import Foundation

/// Static built-in deck for the `.questions` mode (M1). Sourced from the
/// PRD's §15 (safe) and §16 (hot, non-graphic, App Store build) examples.
/// A JSON-backed, localizable catalog is the documented v1.1+ path (PRD §9);
/// M1 ships this in-process so the deck has no file-loading failure mode.
enum ContentCatalog {

    private static let reviewDate: Date = {
        var components = DateComponents()
        components.year = 2026
        components.month = 9
        components.day = 22
        return Calendar(identifier: .gregorian).date(from: components) ?? Date()
    }()

    private static func card(
        id: String,
        kind: CardKind = .question,
        text: String,
        level: Int,
        topics: [Topic],
        consent: [ConsentTopic] = [],
        format: AnswerFormat
    ) -> Card {
        Card(
            id: id,
            mode: .questions,
            kind: kind,
            text: text,
            intensityLevel: level,
            topics: topics,
            playerCountRange: 2...2,
            relationshipFormats: [.any],
            requiredConsent: consent,
            sensitiveTriggers: [],
            answerFormat: format,
            distribution: .appStoreSafe,
            contentVersion: 1,
            locale: "ru",
            lastReviewedAt: reviewDate
        )
    }

    static let questions: [Card] = [

        // MARK: Levels 1-2 — safe, warm

        card(id: "q_001", text: "Какой комплимент от партнёра ты особенно ценишь?", level: 1, topics: [.desires], format: .openText),
        card(id: "q_002", text: "Что для тебя выглядит как идеальное свидание?", level: 1, topics: [.desires], format: .openText),
        card(id: "q_003", text: "Выбери: тихий вечер вдвоём или активное приключение?", level: 1, topics: [.desires], format: .singleChoice),
        card(id: "q_004", text: "Когда ты в последний раз чувствовал(а) себя особенно желанным(ой)?", level: 1, topics: [.desires], format: .openText),
        card(id: "q_005", kind: .dare, text: "Если оба согласны — сделайте друг другу комплимент, глядя в глаза.", level: 1, topics: [.intimacyStyles], format: .discussAfter),
        card(id: "q_006", text: "Тебе нравится, когда вечер спланирован заранее?", level: 1, topics: [.desires], format: .yesNoMaybe),
        card(id: "q_007", text: "Что помогает тебе расслабиться после трудного дня?", level: 1, topics: [.intimacyStyles], format: .openText),
        card(id: "q_008", text: "Назови одно качество партнёра, которое тебя привлекает больше всего.", level: 2, topics: [.desires], format: .privateAnswer),
        card(id: "q_009", text: "Назови место, где было бы приятно провести вечер вдвоём.", level: 1, topics: [.intimacyStyles], format: .simultaneousReveal),
        card(id: "q_010", text: "Объятия, поцелуй или долгий разговор — что сейчас важнее?", level: 1, topics: [.intimacyStyles], format: .singleChoice),
        card(id: "q_011", text: "Какой жест партнёра заставляет тебя улыбнуться?", level: 1, topics: [.intimacyStyles], format: .openText),
        card(id: "q_012", kind: .dare, text: "Если оба согласны — возьмитесь за руки и молча посмотрите друг на друга 10 секунд.", level: 2, topics: [.intimacyStyles], consent: [.physicalContact], format: .discussAfter),
        card(id: "q_013", text: "Что ещё создаёт для тебя романтичное настроение, кроме музыки и свечей?", level: 1, topics: [.intimacyStyles], format: .addOwnOption),
        card(id: "q_014", text: "Оцени от 1 до 5, насколько ты сейчас доволен(льна) нашей близостью.", level: 2, topics: [.intimacyStyles], format: .privateAnswer),
        card(id: "q_015", text: "Какая мелочь в отношениях делает тебя счастливым(ой)?", level: 1, topics: [.desires], format: .openText),

        // MARK: Levels 3-6 — hot, never graphic

        card(id: "q_016", text: "Какая твоя фантазия связана больше с ощущением контроля, чем с конкретным действием?", level: 4, topics: [.fantasy, .dominanceSubmission], format: .openText),
        card(id: "q_017", text: "Кому из вас комфортнее иногда полностью брать инициативу на себя?", level: 4, topics: [.dominanceSubmission], format: .discussAfter),
        card(id: "q_018", text: "Назови одну вещь, о которой давно хотел(а) сказать партнёру, но стеснялся(ась).", level: 4, topics: [.desires], format: .privateAnswer),
        card(id: "q_019", text: "Интересна ли тебе идея смены привычных ролей на один вечер?", level: 4, topics: [.roleplay], format: .yesNoMaybe),
        card(id: "q_020", kind: .dare, text: "Если оба согласны — скажите друг другу фразу, которую обычно приберегаете для особого настроения.", level: 3, topics: [.intimacyStyles], format: .discussAfter),
        card(id: "q_021", text: "Что тебе интереснее — предсказуемый сценарий или спонтанность в близости?", level: 3, topics: [.intimacyStyles], format: .discussAfter),
        card(id: "q_022", text: "Есть ли фантазия, которую тебе проще обсудить, чем предложить попробовать?", level: 5, topics: [.fantasy], format: .openText),
        card(id: "q_023", text: "Что сильнее цепляет — новизна, контроль, внимание или тайна?", level: 4, topics: [.fantasy], format: .singleChoice),
        card(id: "q_024", text: "Как вы относитесь к идее присутствия ещё одного человека в фантазии — не как к плану, а как к теме для разговора?", level: 6, topics: [.multiplePartners], format: .discussAfter),
        card(id: "q_025", text: "Назови фантазию уровня «точно да», одну «может быть» и одну «только фантазия».", level: 5, topics: [.fantasy], format: .privateAnswer),
        card(id: "q_026", text: "Что для тебя означает довериться партнёру полностью хотя бы на один вечер?", level: 4, topics: [.dominanceSubmission], format: .openText),
        card(id: "q_027", text: "Где проходит грань между «дразнить» и «слишком»?", level: 4, topics: [.boundariesAndSafewords], format: .discussAfter),
        card(id: "q_028", kind: .dare, text: "Если оба согласны — предложите друг другу поменяться: кто сегодня ведёт вечер.", level: 4, topics: [.dominanceSubmission], format: .discussAfter),
        card(id: "q_029", text: "Интересна ли тебе тема ролевых игр как способ разнообразить вечер?", level: 3, topics: [.roleplay], format: .yesNoMaybe),
        card(id: "q_030", text: "Как вы относитесь к теме лёгкого доминирования и подчинения как теме для разговора, без обязательства пробовать?", level: 5, topics: [.lightBDSM, .dominanceSubmission], format: .discussAfter)
    ]
}
