def test_rich_renderer_conforms_to_renderer_protocol():
    from keeper_sdk.cli.renderer import RichRenderer
    from keeper_sdk.core.interfaces import Renderer

    r: Renderer = RichRenderer()

    assert hasattr(r, "render_plan")
    assert hasattr(r, "render_diff")
    assert hasattr(r, "render_outcomes")
