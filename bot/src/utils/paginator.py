"""
bot/src/utils/paginator.py
Reusable paginated embed view for slash commands that return long lists.
"""
from __future__ import annotations

from typing import Sequence

import discord


class PaginatedView(discord.ui.View):
    """
    Displays a list of strings across multiple embed pages.
    Each page holds up to `page_size` items.
    Buttons are hidden when not applicable (first/last page).
    """

    def __init__(
        self,
        items: Sequence[str],
        title: str,
        color: discord.Color = discord.Color.blurple(),
        page_size: int = 15,
    ) -> None:
        super().__init__(timeout=120)
        self.items = list(items)
        self.title = title
        self.color = color
        self.page_size = page_size
        self.page = 0
        self.total_pages = max(1, (len(items) + page_size - 1) // page_size)

        self._update_buttons()

    def _current_embed(self) -> discord.Embed:
        start = self.page * self.page_size
        end = start + self.page_size
        chunk = self.items[start:end]
        desc = "\n".join(chunk) if chunk else "*Nothing here.*"
        embed = discord.Embed(
            title=self.title,
            description=desc,
            color=self.color,
        )
        embed.set_footer(text=f"Page {self.page + 1} / {self.total_pages}")
        return embed

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._current_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page = min(self.total_pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._current_embed(), view=self)

    async def send(self, interaction: discord.Interaction) -> None:
        """Send the first page as an ephemeral response."""
        await interaction.response.send_message(
            embed=self._current_embed(), view=self, ephemeral=True
        )
