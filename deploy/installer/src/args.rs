use clap::Parser;

#[derive(Debug, Clone, Parser)]
#[command(name = "installer", version, about = "ComicGUISpider native updater")]
pub struct CliArgs {
    #[arg(long = "uv-exc")]
    pub uv_exc: String,

    #[arg(long)]
    pub version: String,

    #[arg(long = "index-url", default_value_t)]
    pub index_url: String,

    #[arg(long = "parent-pid", default_value_t = 0)]
    pub parent_pid: u32,

    #[arg(long = "uv-tool-dir", default_value_t)]
    pub uv_tool_dir: String,

    #[arg(long = "uv-tool-bin-dir", default_value_t)]
    pub uv_tool_bin_dir: String,

    #[arg(long = "no-gui")]
    pub no_gui: bool,
}
