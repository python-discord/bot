from collections import namedtuple
from string import ascii_lowercase, ascii_uppercase
from textwrap import dedent

import discord

from bot.constants import Roles

Question = namedtuple("question", ("question", "answers"))

questions = [
    Question(
        question="How do you print in python?",
        answers=(
            "`print()`",
            "`sys.stdout.write()`",
            "None of the above",
            "All of the above"
        )
    ),
    Question(
        question=dedent(
            """
            A user opens a help channel with the following information:
            > Help, my code is broken.

            They are in a hurry, so there's no time for back-and-forth debugging the issue.
            Is the solution to their issue:
            """
        ).strip(),
        answers=(
            'Replace `password == "123" or "456"` with `password in ("123", "456")`',
            "Downgrade to 3.10 because `binascii.rldecode_hqx()` was removed in 3.11",
            "Restart their computer and try running it again (it worked before)",
            (
                "Nothing. They weren't actually getting an error, "
                "the import was just greyed out in VSCode because they hadn't used it yet. "
            )
        )
    ),
    Question(
        question="Why is static typing a terrible feature for a programming language?",
        answers=(
            "It makes it more difficult to apply polymorphism",
            "You get TypeErrors before you can even run the code, slowing down development",
            "Guido likes static typing now, actually",
            "All of the above"
        )
    ),
    Question(
        question="When is Lemon Day?",
        answers=(
            "January 1",
            "April 14",
            "August 29",
            "Any day that is not Lime Day"
        )
    )
]

TOTAL_QUESTION_TO_ASK = 4

HELPERS_ROLE = discord.Object(Roles.new_helpers)


def format_question(question_index: int) -> str:
    """Format the question to be displayed in chat."""
    question = questions[question_index]
    prompt = f"**Question {question_index+1} of {TOTAL_QUESTION_TO_ASK}**\n\n{question.question}\n\n"
    prompt += "\n".join(
        f":regional_indicator_{letter}: {answer}"
        for letter, answer in zip(ascii_lowercase, question.answers)
    )
    return prompt


class HelperingView(discord.ui.View):
    """A view that implements the helpering logic by asking a series of questions."""

    def __init__(self, phase: int = 0):
        super().__init__()
        print(phase)
        self.phase = phase

        answers_view = AnswersSelect(phase)
        self.add_item(answers_view)


class AnswersSelect(discord.ui.Select):
    """A selection of answers to the given question."""

    def __init__(self, phase: int):
        question = questions[phase]
        answers = [discord.SelectOption(label=answer) for answer in ascii_uppercase[:len(question.answers)]]

        super().__init__(options=answers)
        self.phase = phase

    async def callback(self, interaction: discord.Interaction) -> None:
        """Move to the next question, or apply the role if enough question were answered."""
        if self.phase + 1 >= TOTAL_QUESTION_TO_ASK:
            if isinstance(interaction.user, discord.Member):
                await interaction.user.add_roles(HELPERS_ROLE)
                await interaction.response.edit_message(
                    content=":white_check_mark: Added the Helpers role!", view=None
                )
        else:
            content = format_question(self.phase + 1)
            view = HelperingView(self.phase + 1)
            await interaction.response.edit_message(content=content, view=view)

        self.view.stop()


class HelperingButton(discord.ui.Button):
    """The button which starts the helpering process."""

    def __init__(self, assigned: bool, row: int,):
        label = "Add role Helpers" if not assigned else "Remove role Helpers"
        style = discord.ButtonStyle.green if not assigned else discord.ButtonStyle.red
        super().__init__(style=style, label=label, row=row)
        self.assigned = assigned

    async def callback(self, interaction: discord.Interaction) -> None:
        """Either remove the Helpers role or start the Helpering process."""
        if self.assigned:
            if isinstance(interaction.user, discord.Member):
                await interaction.user.remove_roles(HELPERS_ROLE)
                self.label = "Add role Helpers"
                self.style = discord.ButtonStyle.green
                self.assigned = not self.assigned
                await interaction.response.edit_message(view=self.view)
                await interaction.followup.send("Removed role Helpers", ephemeral=True)
            return

        await interaction.response.edit_message(content="Launching Helpering process, good luck!", view=None)
        content = format_question(0)
        view = HelperingView()
        await interaction.followup.send(
            content=content,
            view=view,
            ephemeral=True,
        )
        self.view.stop()
