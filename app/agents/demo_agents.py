from app.agents.base import BaseAgent


class ResearchAgent(BaseAgent):
    name = "research"

    async def run(self, input_data):
        topic = input_data["topic"]
        return {
            "topic": topic,
            "keywords": [topic, f"{topic} explained", f"future of {topic}"],
            "audience_questions": [f"Why does {topic} matter?", f"What changes next?"],
            "content_gaps": [f"Practical angle on {topic}"],
            "sources": [],
        }


class ScriptAgent(BaseAgent):
    name = "script"

    async def run(self, input_data):
        research = input_data["research"]
        topic = research["topic"]
        return {
            "title": f"{topic}: What Happens Next?",
            "hook": f"Most people are looking at {topic} the wrong way.",
            "sections": [
                {"type": "hook", "duration": 6, "text": f"Most people are looking at {topic} the wrong way."},
                {"type": "context", "duration": 8, "text": f"Here is the context behind {topic}."},
                {"type": "main", "duration": 14, "text": f"Three changes are likely to matter most for {topic}."},
                {"type": "conclusion", "duration": 7, "text": "The important point is what we do next."},
            ],
        }


class StoryboardAgent(BaseAgent):
    name = "storyboard"

    async def run(self, input_data):
        script = input_data["script"]
        scenes = []
        for i, section in enumerate(script["sections"], start=1):
            scenes.append({
                "scene": i,
                "duration": section["duration"],
                "narration": section["text"],
                "visual": f"B-roll / generated visual for {section['type']}",
                "on_screen_text": section["type"].upper(),
            })
        return {"scenes": scenes}


class ProductionAgent(BaseAgent):
    name = "production"

    async def run(self, input_data):
        storyboard = input_data["storyboard"]
        return {
            "assets": [
                {"id": f"asset_{i}", "scene": scene["scene"], "type": "generated_placeholder", "status": "ready"}
                for i, scene in enumerate(storyboard["scenes"], start=1)
            ]
        }


class EditorAgent(BaseAgent):
    name = "editor"

    async def run(self, input_data):
        return {"render_status": "ready_for_renderer"}


class QAAgent(BaseAgent):
    name = "qa"

    async def run(self, input_data):
        editor = input_data["editor"]
        output_path = editor.get("output_path")
        return {
            "approved": bool(output_path),
            "issues": [] if output_path else ["Rendered output is missing"],
        }
