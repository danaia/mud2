import os
import json
import random
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

@dataclass
class Item:
    name: str
    description: str
    can_take: bool = True
    
@dataclass
class Room:
    name: str
    description: str
    items: List[Item]
    exits: Dict[str, str]  # direction: room_name
    visited: bool = False
    hints: List[str] = None
    atmosphere: str = ""
    story_context: str = ""  # Add story context for narrative continuity
    is_goal: bool = False    # Indicates if this is a goal room

class Player:
    def __init__(self, name: str):
        self.name = name
        self.inventory: List[Item] = []
        self.current_room: Optional[str] = None
        
    def take_item(self, item: Item) -> bool:
        if item.can_take:
            self.inventory.append(item)
            return True
        return False

class Game:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.player: Optional[Player] = None
        self.story_theme: str = ""
        self.goal_description: str = ""
        self.current_path_depth: int = 0
        self.max_path_depth: int = 10  # Maximum rooms before reaching a goal
        
    async def initialize_game(self):
        """Initialize the game world with a randomly generated story theme."""
        # Generate overall story theme and goal
        await self.generate_story_theme()
        
        # Create initial room
        starting_room = await self.generate_room("start", None)
        self.rooms["start"] = starting_room
        
        # Create player
        self.player = Player("Adventurer")
        self.player.current_room = "start"

    async def generate_story_theme(self):
        """Generate the overall story theme and goal using OpenAI."""
        prompt = """Create a unique adventure story theme with a clear goal for a text adventure game.
        Format as JSON with:
        {
            "theme": "overall story theme",
            "goal": "specific goal the player needs to achieve",
            "backstory": "brief backstory that sets up the adventure"
        }
        Make it engaging and suitable for a text adventure with multiple possible paths."""

        try:
            client = openai.AsyncOpenAI()
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a creative game narrative designer."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            story_data = json.loads(response.choices[0].message.content)
            self.story_theme = story_data["theme"]
            self.goal_description = story_data["goal"]
            
            print("\nYour Quest Begins...")
            print(f"\n{story_data['backstory']}")
            print(f"\nYour Goal: {self.goal_description}\n")
            
        except Exception as e:
            print(f"Error generating story theme: {e}")
            self.story_theme = "A mysterious adventure"
            self.goal_description = "Discover the truth and find your way home"

    async def generate_room(self, room_id: str, previous_room: Optional[Room]) -> Room:
        """Generate a room that continues the story coherently."""
        story_context = f"""
        Story Theme: {self.story_theme}
        Ultimate Goal: {self.goal_description}
        Current Path Depth: {self.current_path_depth}/{self.max_path_depth}
        Previous Room Context: {previous_room.story_context if previous_room else 'Starting point'}
        """

        prompt = f"""Generate a detailed room description that continues the story.
        Current story context: {story_context}
        
        Format response as JSON with:
        {{
            "name": "room name",
            "description": "main room description",
            "atmosphere": "ambient details, sounds, smells, feelings",
            "items": [
                {{"name": "item name", "description": "item description", "can_take": boolean}}
            ],
            "hints": [
                "subtle hint about possible paths or choices"
            ],
            "story_context": "how this room connects to the overall narrative",
            "suggested_exits": {{
                "direction": "brief description of what lies in that direction"
            }},
            "is_goal": boolean
        }}
        
        Ensure the room connects logically to the previous context and offers 2-4 meaningful choices for progression.
        If current_path_depth is near max_path_depth, consider making this a potential goal room if it fits the narrative."""

        try:
            client = openai.AsyncOpenAI()
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a master storyteller crafting an interconnected narrative."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            room_data = json.loads(response.choices[0].message.content)
            items = [Item(**item) for item in room_data["items"]]
            
            # Generate connected rooms based on suggested exits
            exits = {}
            for direction, desc in room_data["suggested_exits"].items():
                new_room_id = f"{room_id}_{direction}"
                exits[direction] = new_room_id
                
            room = Room(
                name=room_data["name"],
                description=room_data["description"],
                items=items,
                exits=exits,
                visited=False,
                hints=room_data.get("hints", []),
                atmosphere=room_data.get("atmosphere", ""),
                story_context=room_data.get("story_context", ""),
                is_goal=room_data.get("is_goal", False)
            )
            
            return room
            
        except Exception as e:
            print(f"Error generating room: {e}")
            return self.create_fallback_room(room_id)

    def create_fallback_room(self, room_id: str) -> Room:
        """Create a basic room when API generation fails."""
        exits = {"forward": f"{room_id}_forward", "back": "start"}
        return Room(
            name="Mysterious Chamber",
            description="A mysterious chamber with shifting walls.",
            items=[],
            exits=exits,
            hints=["The path ahead seems to pulse with energy."],
            atmosphere="The air crackles with unknown forces.",
            story_context="A mysterious point in your journey."
        )

    async def handle_room_transition(self, direction: str) -> str:
        """Handle movement between rooms, generating new rooms as needed."""
        current_room = self.rooms[self.player.current_room]
        if direction not in current_room.exits:
            return "You can't go that way."
            
        next_room_id = current_room.exits[direction]
        
        # Generate the new room if it doesn't exist
        if next_room_id not in self.rooms:
            self.current_path_depth += 1
            new_room = await self.generate_room(next_room_id, current_room)
            self.rooms[next_room_id] = new_room
            
        self.player.current_room = next_room_id
        
        # Check if player reached a goal room
        if self.rooms[next_room_id].is_goal:
            return self.handle_goal_room()
            
        return self.cmd_look()

    def handle_goal_room(self) -> str:
        """Handle when player reaches a goal room."""
        room = self.rooms[self.player.current_room]
        return f"""
{room.description}

Congratulations! {self.goal_description}

You have completed your quest! Would you like to:
1. Continue exploring
2. Start a new adventure (type 'quit' and restart)
"""

    async def cmd_move(self, direction: str) -> str:
        """Enhanced movement command with room generation."""
        return await self.handle_room_transition(direction)

    async def process_command(self, command: str) -> str:
        """Process player commands with enhanced hint system."""
        words = command.lower().split()
        if not words:
            return "Please enter a command."
            
        verb = words[0]
        noun = words[1] if len(words) > 1 else ""
        
        if verb == "look":
            return self.cmd_look()
        elif verb == "inventory" or verb == "i":
            return self.cmd_inventory()
        elif verb in ["n", "s", "e", "w", "north", "south", "east", "west"]:
            return await self.cmd_move(verb)
        elif verb == "take" and noun:
            return self.cmd_take(noun)
        elif verb == "help":
            return self.cmd_help()
        elif verb == "hint":
            return await self.get_contextual_hint()
        elif verb == "examine" and noun:
            return self.cmd_examine(noun)
        else:
            return "I don't understand that command."

    def cmd_look(self) -> str:
        """Enhanced look command with atmospheric details and hints."""
        room = self.rooms[self.player.current_room]
        
        # Build the description with multiple components
        description_parts = [
            f"\n{room.name.upper()}\n",
            room.description,
            f"\n{room.atmosphere}",  # Add atmospheric details
            "\n"
        ]
        
        # Add item descriptions
        if room.items:
            items_desc = "\n".join([f"There is {item.name} here." for item in room.items])
            description_parts.append(items_desc)
        
        # Add exits
        exits_desc = "Exits: " + ", ".join(room.exits.keys()) if room.exits else "There are no obvious exits."
        description_parts.append(f"\n{exits_desc}")
        
        # Add hints if the room hasn't been visited before
        if not room.visited:
            if room.hints:
                description_parts.append("\nAs you take in your surroundings, you notice:")
                for hint in room.hints:
                    description_parts.append(f"- {hint}")
            room.visited = True
        
        return "\n".join(description_parts)

    def cmd_inventory(self) -> str:
        """Handle the inventory command."""
        if not self.player.inventory:
            return "You are empty-handed."
        return "You are carrying:\n" + "\n".join([f"- {item.name}" for item in self.player.inventory])

    def cmd_take(self, item_name: str) -> str:
        """Handle take command."""
        room = self.rooms[self.player.current_room]
        for item in room.items:
            if item.name.lower() == item_name:
                if self.player.take_item(item):
                    room.items.remove(item)
                    return f"Taken: {item.name}"
                return f"You can't take the {item.name}."
        return f"I don't see a {item_name} here."

    def cmd_help(self) -> str:
        """Enhanced help command."""
        return """Available commands:
        - look: Examine your surroundings in detail
        - inventory (or i): Check your inventory
        - take [item]: Pick up an item
        - examine [item/direction]: Look at something more closely
        - n/s/e/w: Move in a direction
        - hint: Get a contextual hint about what to try next
        - help: Show this help message
        - quit: Exit the game"""

    async def get_contextual_hint(self) -> str:
        """Get a contextual hint based on the current game state."""
        room = self.rooms[self.player.current_room]
        
        context = f"""
        Current room: {room.name}
        Description: {room.description}
        Items present: {', '.join(item.name for item in room.items)}
        Inventory: {', '.join(item.name for item in self.player.inventory)}
        Available exits: {', '.join(room.exits.keys())}
        """
        
        try:
            client = openai.AsyncOpenAI()
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful game guide providing gentle hints."},
                    {"role": "user", "content": f"Based on this game state, provide a subtle hint about what the player might try next:\n{context}"}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return "You might want to examine your surroundings more carefully..."

    def cmd_examine(self, target: str) -> str:
        """Handle examining items or features in detail."""
        room = self.rooms[self.player.current_room]
        
        # Check inventory items
        for item in self.player.inventory:
            if item.name.lower() == target.lower():
                return item.description
        
        # Check room items
        for item in room.items:
            if item.name.lower() == target.lower():
                return item.description
        
        return f"You don't see anything special about the {target}."

async def main():
    while True:
        game = Game()
        await game.initialize_game()
        
        print("Welcome to the AI-powered Text Adventure!")
        print("Type 'help' for a list of commands.")
        print("\n" + game.cmd_look())
        
        while True:
            try:
                command = input("\n> ").strip()
                if command.lower() == "quit":
                    print("Thanks for playing!")
                    break
                    
                response = await game.process_command(command)
                print("\n" + response)
                
            except KeyboardInterrupt:
                print("\nThanks for playing!")
                break
            except Exception as e:
                print(f"An error occurred: {e}")
        
        play_again = input("\nWould you like to play again? (yes/no): ").lower()
        if play_again != "yes":
            break

if __name__ == "__main__":
    asyncio.run(main())
