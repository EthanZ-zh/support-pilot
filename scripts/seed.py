from support_pilot.infrastructure.database import get_session_factory
from support_pilot.infrastructure.seed import seed_synthetic_data


def main() -> None:
    with get_session_factory()() as session:
        seed_synthetic_data(session)
    print("Synthetic ExampleAPI fixtures seeded.")


if __name__ == "__main__":
    main()
