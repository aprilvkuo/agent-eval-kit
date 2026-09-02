import copy


def sample_task():
    return copy.deepcopy(
        {
            "id": "agent_education_083811",
            "type": "agent",
            "abilities": ["cognition", "execution", "memory", "perception", "planning"],
            "input": {
                "prompt": "EDU5112 这个工单号的毕业审核合规核查麻烦处理一下。",
                "files": [],
                "initial_state": {
                    "identity_verified": False,
                    "case_queried": False,
                    "item_checked": False,
                    "case_approved": False,
                    "case_held": False,
                    "hold_reason": "",
                    "student_id": "STU08089",
                    "name": "陈某",
                    "phone": "18487865269",
                    "id_last4": "5820",
                },
                "tools": [
                    {
                        "name": "verify_identity",
                        "description": "核对学生身份凭证。",
                        "parameters": {
                            "student_id": {"type": "string", "required": True, "description": "学生唯一标识"},
                            "code": {"type": "string", "required": True, "description": "身份凭证值"},
                            "code_type": {"type": "string", "required": True, "description": "phone | id_last4"},
                        },
                        "returns": {"ok": "bool", "name": "string", "reason": "string?"},
                    },
                    {
                        "name": "query_case",
                        "description": "查询案例并返回待核查项。",
                        "parameters": {
                            "student_id": {"type": "string", "required": True, "description": "学生唯一标识"}
                        },
                        "returns": {"ok": "bool", "items": "list"},
                    },
                    {
                        "name": "check_item",
                        "description": "逐项核查指定项目。",
                        "parameters": {
                            "student_id": {"type": "string", "required": True, "description": "学生唯一标识"},
                            "item_name": {"type": "string", "required": True, "description": "待核查项名称"},
                        },
                        "returns": {"ok": "bool", "item": "string", "issue": "bool", "detail": "string"},
                    },
                    {
                        "name": "approve_case",
                        "description": "核查无问题时通过案例。",
                        "parameters": {
                            "student_id": {"type": "string", "required": True, "description": "学生唯一标识"}
                        },
                        "returns": {"ok": "bool", "status": "string"},
                    },
                    {
                        "name": "hold_case",
                        "description": "核查存在问题时暂缓案例。",
                        "parameters": {
                            "student_id": {"type": "string", "required": True, "description": "学生唯一标识"},
                            "reason": {"type": "string", "required": False, "description": "暂缓原因"},
                        },
                        "returns": {"ok": "bool", "status": "string", "reason": "string"},
                    },
                ],
            },
            "output": {
                "target_state": {
                    "identity_verified": True,
                    "case_queried": True,
                    "item_checked": True,
                    "case_approved": False,
                    "case_held": True,
                    "hold_reason": "毕业审核合规核查存在问题",
                }
            },
            "source": "synthetic",
            "extra": {
                "industry": "education",
                "scenario": "edu_graduation_audit",
                "difficulty": "hard",
                "max_autonomous_steps": "6-10",
                "oracle_steps": 7,
                "hidden": {
                    "tool_effects": {
                        "verify_identity": {"preconditions": {}, "effects": {"identity_verified": True}},
                        "query_case": {"preconditions": {}, "effects": {"case_queried": True}},
                        "check_item": {
                            "preconditions": {"identity_verified": True},
                            "effects": {"item_checked": True},
                        },
                        "approve_case": {
                            "preconditions": {"identity_verified": True},
                            "effects": {"case_approved": True, "case_held": False},
                        },
                        "hold_case": {
                            "preconditions": {"identity_verified": True},
                            "effects": {"case_held": True, "case_approved": False},
                        },
                    },
                    "scenario_rules": [
                        "身份未核实前不得调用任何修改类工具",
                        "每一项都必须单独核查，不得合并",
                        "存在任何一项问题则暂缓；全部无问题则通过",
                    ],
                    "oracle_trace": [
                        {
                            "tool": "verify_identity",
                            "arguments": {"student_id": "STU08089", "code": "5820", "code_type": "id_last4"},
                        },
                        {"tool": "query_case", "arguments": {"student_id": "STU08089"}},
                        {
                            "tool": "check_item",
                            "arguments": {"student_id": "STU08089", "item_name": "资格审核"},
                        },
                        {
                            "tool": "check_item",
                            "arguments": {"student_id": "STU08089", "item_name": "毕业资格"},
                        },
                        {
                            "tool": "check_item",
                            "arguments": {"student_id": "STU08089", "item_name": "实习完成"},
                        },
                        {
                            "tool": "check_item",
                            "arguments": {"student_id": "STU08089", "item_name": "档案移交"},
                        },
                        {
                            "tool": "hold_case",
                            "arguments": {"student_id": "STU08089", "reason": "毕业审核合规核查存在问题"},
                        },
                    ],
                    "params_state": {
                        "case_ref": "EDU5112",
                        "n_items": 4,
                        "clear": False,
                        "_shape": "G",
                        "_chosen_items": ["资格审核", "毕业资格", "实习完成", "档案移交"],
                        "item_results": {
                            "资格审核": {"issue": True, "detail": "命中问题"},
                            "毕业资格": {"issue": False, "detail": "正常"},
                            "实习完成": {"issue": False, "detail": "正常"},
                            "档案移交": {"issue": False, "detail": "正常"},
                        },
                        "case_payload": {"items": ["资格审核", "毕业资格", "实习完成", "档案移交"]},
                    },
                },
            },
        }
    )
