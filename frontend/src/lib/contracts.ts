export interface OptimizeCodeRequest {
  cpp_code: string;
  stdin_data: string;
  max_self_correction_attempts: number;
}

export interface ComplexityComparison {
  original_time_complexity: string;
  optimized_time_complexity: string;
  original_space_complexity: string;
  optimized_space_complexity: string;
  estimated_speedup_ratio: number;
}

export interface CompilationAttempt {
  attempt: number;
  success: boolean;
  compiler_stdout: string;
  compiler_stderr: string;
  run_stdout: string | null;
  run_stderr: string | null;
  exit_code: number | null;
}

export interface ChartPoint {
  input_size: number;
  brute_force_ops: number;
  optimized_ops: number;
}

export interface RechartsVisualization {
  chart_type: "line";
  chart_title: string;
  x_key: "input_size";
  y_keys: Array<"brute_force_ops" | "optimized_ops">;
  points: ChartPoint[];
}

export interface SwarmOptimizationResult {
  status: "success" | "failed";
  problem_summary: string;
  original_code: string;
  optimized_code: string;
  complexity: ComplexityComparison;
  algorithm_choices: string[];
  optimization_notes: string[];
  correctness_notes: string;
  compiler_attempts: CompilationAttempt[];
  visualization: RechartsVisualization;
}

export interface OptimizeCodeResponse {
  request_id: string;
  result: SwarmOptimizationResult;
}

export interface ApiErrorPayload {
  error?: string;
  detail?: string;
  backend?: unknown;
}
