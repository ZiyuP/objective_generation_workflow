"""Entry point — run the AutismGPT Lesson Creation Agent."""
from autism_gpt.agent import LessonCreationAgent


def main() -> None:
    agent = LessonCreationAgent()
    agent.run()


if __name__ == "__main__":
    main()
