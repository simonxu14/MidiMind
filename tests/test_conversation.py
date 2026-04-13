from arranger.conversation import ConversationManager, ProcessingStep


def test_get_processing_steps_reads_from_manager_storage(tmp_path):
    manager = ConversationManager(storage_dir=tmp_path)
    conversation_id = manager.create_conversation("write a chamber version")

    manager.add_processing_step(
        conversation_id,
        ProcessingStep(
            step_name="midi_analysis",
            input_data={"file": "demo.mid"},
            output_data={"tempo": 120},
        ),
    )

    steps = manager.get_processing_steps(conversation_id)

    assert len(steps) == 1
    assert steps[0]["step_name"] == "midi_analysis"


def test_update_metadata_merges_into_existing_conversation(tmp_path):
    manager = ConversationManager(storage_dir=tmp_path)
    conversation_id = manager.create_conversation("write a chamber version", metadata={"source": "upload"})

    manager.update_metadata(
        conversation_id,
        {"last_midi_analysis": {"tempo": 120}, "provider": "minimax"},
    )

    conversation = manager.get_conversation(conversation_id)
    assert conversation["metadata"] == {
        "source": "upload",
        "last_midi_analysis": {"tempo": 120},
        "provider": "minimax",
    }


def test_update_latest_plan_rewrites_latest_version_when_present(tmp_path):
    manager = ConversationManager(storage_dir=tmp_path)
    conversation_id = manager.create_conversation("write a chamber version")
    manager.add_arrangement_version(conversation_id, {"transform": {"type": "orchestration"}})

    manager.update_latest_plan(
        conversation_id,
        {"transform": {"type": "orchestration"}, "ensemble": {"parts": [{"id": "piano"}]}},
    )

    latest_version = manager.get_latest_version(conversation_id)
    assert latest_version["plan"] == {
        "transform": {"type": "orchestration"},
        "ensemble": {"parts": [{"id": "piano"}]},
    }


def test_add_arrangement_version_persists_generation_intent(tmp_path):
    manager = ConversationManager(storage_dir=tmp_path)
    conversation_id = manager.create_conversation("write a chamber version")

    version_id = manager.add_arrangement_version(
        conversation_id,
        {"transform": {"type": "orchestration"}},
        generation_intent="make it brighter",
    )

    latest_version = manager.get_latest_version(conversation_id)
    assert latest_version["version_id"] == version_id
    assert latest_version["generation_intent"] == "make it brighter"
