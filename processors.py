from datetime import datetime
from typing import List
import json

from pipecat.frames.frames import (
    Frame,
    UserStoppedSpeakingFrame,
    TranscriptionFrame,
    InterimTranscriptionFrame,
    UserStartedSpeakingFrame,
    LLMResponseEndFrame,
    LLMFullResponseEndFrame,
)
from pipecat.processors.aggregators.llm_response import LLMResponseAggregator
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

from loguru import logger

class ConversationLogger(FrameProcessor):
    def __init__(self, messages: List[dict], log_file_path: str):
        super().__init__()
        self.messages = messages
        self.log_file_path = log_file_path
        self.last_logged_index = -1

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, LLMFullResponseEndFrame) or isinstance(frame, UserStoppedSpeakingFrame):
            self.log_messages()
        await self.push_frame(frame, direction)


    def log_messages(self):
        new_messages = self.messages[self.last_logged_index + 1:]
        if new_messages:
            with open(self.log_file_path, 'a') as log_file:
                for message in new_messages:
                    json.dump(message, log_file, indent=4)
                    log_file.write(',\n')
            self.last_logged_index = len(self.messages) - 1
            logger.info(f"Logged {len(new_messages)} new messages to {self.log_file_path}")

class ConversationProcessor(LLMResponseAggregator):
    """
    This frame processor keeps track of a conversation by capturing TranscriptionFrames
    and aggregating the text along with timestamps and user IDs in a conversation array.

    Attributes:
        conversation (list): A list of dictionaries containing conversation entries.
        user_mapping (dict): A dictionary mapping user_ids to participant names.
    """

    def __init__(self, messages: List[dict] = []):
        super().__init__(
            messages=messages,
            role="user",
            start_frame=UserStartedSpeakingFrame,
            end_frame=UserStoppedSpeakingFrame,
            accumulator_frame=TranscriptionFrame,
            interim_accumulator_frame=InterimTranscriptionFrame
        )
        self._aggregation_detailed = []
        self.user_mapping = {}

    def add_user_mapping(self, user_id: str, participant_name: str):
        """
        Stores a mapping between user_id and participant_name.

        Args:
            user_id (str): The user's ID.
            participant_name (str): The participant's name.
        """
        self.user_mapping[user_id] = participant_name

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, self._accumulator_frame):
            if self._aggregating:
                # timestamp has the format "2024-07-14T10:18:19.766929Z"
                # parse it into a datetime object
                timestamp = datetime.fromisoformat(frame.timestamp[:-1])
                entry = {
                    "user_id": frame.user_id,
                    "text": frame.text,
                    "timestamp": timestamp
                }
                self._aggregation_detailed.append(entry)

    async def _push_aggregation(self):
        self._aggregation = self.format_aggregation()
        self._aggregation_detailed = []
        await super()._push_aggregation()

    def format_aggregation(self):
        """
        Formats the aggregation into a multi-line string.
        """
        formatted = []
        for entry in self._aggregation_detailed:
            user_id = entry['user_id']
            username = self.user_mapping.get(user_id, user_id)  # Use username if available, otherwise use user_id
            timestamp = entry['timestamp'].strftime("%H:%M:%S")
            formatted.append(f"{timestamp} | {username} | {entry['text']}")
        return "\n".join(formatted)
