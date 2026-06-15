#include "register_allocator.h"

#include <cassert>
#include <cstdlib>
#include <fstream>
#include <fmt/core.h>

namespace
{
constexpr std::array<const char*, RegisterAllocator::ZERO_READ_CATEGORY_COUNT> ZERO_READ_CATEGORY_NAMES = {
    "unknown",           "gpr",                 "stack_pointer",       "flags",           "instruction_pointer", "store",
    "branch_direct_jump", "branch_indirect",    "branch_conditional",  "branch_direct_call", "branch_indirect_call", "branch_return",
    "branch_other",      "trace_entry",
};

std::ofstream& zero_read_log_stream()
{
  static std::ofstream stream;
  static bool initialized = false;
  if (!initialized) {
    initialized = true;
    if (const char* path = std::getenv("CHAMPSIM_ZERO_READ_LOG")) {
      stream.open(path, std::ios::out | std::ios::trunc);
    }
  }
  return stream;
}
} // namespace

RegisterAllocator::RegisterAllocator(size_t num_physical_registers)
{
  assert(num_physical_registers <= std::numeric_limits<PHYSICAL_REGISTER_ID>::max());
  for (size_t i = 0; i < num_physical_registers; ++i) {
    free_registers.push(static_cast<PHYSICAL_REGISTER_ID>(i));
  }
  physical_register_file = std::vector<physical_register>(num_physical_registers);
  read_counts = std::vector<uint32_t>(num_physical_registers, 0);
  frontend_RAT.fill(-1); // default value for no mapping
  backend_RAT.fill(-1);
}

reg_write_kind RegisterAllocator::classify_producer(const ooo_model_instr& producer, int16_t arch_reg)
{
  if (arch_reg == champsim::REG_STACK_POINTER) {
    return reg_write_kind::stack_pointer;
  }
  if (arch_reg == champsim::REG_FLAGS) {
    return reg_write_kind::flags;
  }
  if (arch_reg == champsim::REG_INSTRUCTION_POINTER) {
    return reg_write_kind::instruction_pointer;
  }
  if (!producer.destination_memory.empty()) {
    return reg_write_kind::store;
  }
  if (producer.is_branch) {
    return reg_write_kind::branch;
  }
  return reg_write_kind::gpr;
}

std::size_t RegisterAllocator::zero_read_category_index(const physical_register& meta)
{
  switch (meta.producer_kind) {
  case reg_write_kind::unknown:
    return 0;
  case reg_write_kind::gpr:
    return 1;
  case reg_write_kind::stack_pointer:
    return 2;
  case reg_write_kind::flags:
    return 3;
  case reg_write_kind::instruction_pointer:
    return 4;
  case reg_write_kind::store:
    return 5;
  case reg_write_kind::branch: {
    const auto branch_idx = static_cast<std::size_t>(meta.producer_branch);
    if (branch_idx >= static_cast<std::size_t>(NOT_BRANCH)) {
      return 0;
    }
    return 6 + branch_idx;
  }
  case reg_write_kind::trace_entry:
    return 13;
  }
  return 0;
}

void RegisterAllocator::record_lifetime_reads(PHYSICAL_REGISTER_ID physreg, uint32_t reads)
{
  const auto& meta = physical_register_file.at(physreg);

  // Only count GPR lifetimes; exclude special registers, stores, branches, and trace-entry mappings.
  if (meta.producer_kind != reg_write_kind::gpr) {
    return;
  }

  const std::size_t bucket = reads >= 3 ? 3 : reads;
  ++read_before_overwrite_histogram.at(bucket);

  if (reads != 0) {
    return;
  }

  ++zero_read_lifetime_total;
  const auto category = zero_read_category_index(meta);
  ++zero_read_by_category.at(category);

  if (auto& log = zero_read_log_stream(); log.is_open()) {
    log << fmt::format("ip={} arch_reg={} category={} producer_id={}\n", meta.producer_ip, meta.arch_reg_index,
                       ZERO_READ_CATEGORY_NAMES.at(category), meta.producing_instruction_id);
  }
}

void RegisterAllocator::reset_register_lifetime_histogram()
{
  read_before_overwrite_histogram = {};
  zero_read_by_category = {};
  zero_read_lifetime_total = 0;
}

void RegisterAllocator::print_register_lifetime_histogram() const
{
  const auto total = read_before_overwrite_histogram[0] + read_before_overwrite_histogram[1] + read_before_overwrite_histogram[2]
                     + read_before_overwrite_histogram[3];
  fmt::print("Register reads before overwrite histogram (GPR lifetimes only, total: {})\n", total);
  fmt::print("  0 reads: {}\n", read_before_overwrite_histogram[0]);
  fmt::print("  1 read:  {}\n", read_before_overwrite_histogram[1]);
  fmt::print("  2 reads: {}\n", read_before_overwrite_histogram[2]);
  fmt::print("  3+ reads: {}\n", read_before_overwrite_histogram[3]);
}

void RegisterAllocator::print_zero_read_producer_breakdown() const
{
  if (zero_read_lifetime_total == 0) {
    return;
  }

  const auto all_lifetimes = read_before_overwrite_histogram[0] + read_before_overwrite_histogram[1] + read_before_overwrite_histogram[2]
                           + read_before_overwrite_histogram[3];

  fmt::print("Zero-read GPR lifetimes (total zero-read GPR lifetimes: {})\n", zero_read_lifetime_total);
  fmt::print("  (GPR register values overwritten before any rename-time read.)\n");

  for (std::size_t i = 0; i < ZERO_READ_CATEGORY_COUNT; ++i) {
    const auto count = zero_read_by_category.at(i);
    if (count == 0) {
      continue;
    }
    fmt::print("  {:>22}: {:>12} ({:5.2f}% of zero-read, {:5.2f}% of all lifetimes)\n", ZERO_READ_CATEGORY_NAMES.at(i), count,
                 100.0 * static_cast<double>(count) / static_cast<double>(zero_read_lifetime_total),
                 100.0 * static_cast<double>(count) / static_cast<double>(all_lifetimes));
    fmt::print("ZERO_READ_PROD category={} count={}\n", ZERO_READ_CATEGORY_NAMES.at(i), count);
  }

  if (zero_read_log_stream().is_open()) {
    fmt::print("  Detailed zero-read events written to CHAMPSIM_ZERO_READ_LOG\n");
  } else {
    fmt::print("  Set CHAMPSIM_ZERO_READ_LOG=/path/to/file to log each zero-read producer ip/arch_reg/category\n");
  }
}

PHYSICAL_REGISTER_ID RegisterAllocator::rename_dest_register(int16_t reg, champsim::program_ordered<ooo_model_instr>::id_type producer_id)
{
  assert(!free_registers.empty());

  PHYSICAL_REGISTER_ID phys_reg = free_registers.front();
  free_registers.pop();
  frontend_RAT[reg] = phys_reg;
  physical_register_file.at(phys_reg) = {static_cast<uint16_t>(reg), producer_id, false, true, champsim::address{}, reg_write_kind::unknown,
                                         NOT_BRANCH};
  read_counts.at(phys_reg) = 0;

  return phys_reg;
}

PHYSICAL_REGISTER_ID RegisterAllocator::rename_dest_register(int16_t reg, const ooo_model_instr& producer, int16_t arch_reg)
{
  assert(!free_registers.empty());

  PHYSICAL_REGISTER_ID phys_reg = free_registers.front();
  free_registers.pop();
  frontend_RAT[reg] = phys_reg;

  physical_register_file.at(phys_reg) = {static_cast<uint16_t>(arch_reg),
                                         producer.instr_id,
                                         false,
                                         true,
                                         producer.ip,
                                         classify_producer(producer, arch_reg),
                                         producer.is_branch ? producer.branch : NOT_BRANCH};
  read_counts.at(phys_reg) = 0;

  return phys_reg;
}

PHYSICAL_REGISTER_ID RegisterAllocator::rename_src_register(int16_t reg)
{
  PHYSICAL_REGISTER_ID phys = frontend_RAT[reg];

  if (phys < 0) {
    // allocate the register if it hasn't yet been mapped
    // (common due to the traces being slices in the middle of a program)
    phys = free_registers.front();
    free_registers.pop();
    frontend_RAT[reg] = phys;
    backend_RAT[reg] = phys; // we assume this register's last write has been committed
    physical_register_file.at(phys) = {static_cast<uint16_t>(reg), 0, true, true, champsim::address{}, reg_write_kind::trace_entry, NOT_BRANCH};
    read_counts.at(phys) = 0;
  } else {
    ++read_counts.at(phys);
  }

  return phys;
}

void RegisterAllocator::complete_dest_register(PHYSICAL_REGISTER_ID physreg)
{
  // mark the physical register as valid
  physical_register_file.at(physreg).valid = true;
}

void RegisterAllocator::retire_dest_register(PHYSICAL_REGISTER_ID physreg)
{
  // grab the arch reg index, find old phys reg in backend RAT
  uint16_t arch_reg = physical_register_file.at(physreg).arch_reg_index;
  PHYSICAL_REGISTER_ID old_phys_reg = backend_RAT[arch_reg];

  // update the backend RAT with the new phys reg
  backend_RAT[arch_reg] = physreg;

  // free the old phys reg
  if (old_phys_reg != -1) {
    record_lifetime_reads(old_phys_reg, read_counts.at(old_phys_reg));
    free_register(old_phys_reg);
  }
}

void RegisterAllocator::free_register(PHYSICAL_REGISTER_ID physreg)
{
  physical_register_file.at(physreg) = {255, 0, false, false, champsim::address{}, reg_write_kind::unknown, NOT_BRANCH};
  read_counts.at(physreg) = 0;
  free_registers.push(physreg);
}

bool RegisterAllocator::isValid(PHYSICAL_REGISTER_ID physreg) const { return physical_register_file.at(physreg).valid; }

bool RegisterAllocator::isAllocated(PHYSICAL_REGISTER_ID archreg) const { return frontend_RAT[archreg] != -1; }

unsigned long RegisterAllocator::count_free_registers() const { return std::size(free_registers); }

int RegisterAllocator::count_reg_dependencies(const ooo_model_instr& instr) const
{
  return static_cast<int>(std::count_if(std::begin(instr.source_registers), std::end(instr.source_registers), [this](auto reg) { return !isValid(reg); }));
}

void RegisterAllocator::reset_frontend_RAT()
{
  std::copy(std::begin(backend_RAT), std::end(backend_RAT), std::begin(frontend_RAT));
  // once wrong path is implemented:
  // find registers allocated by wrong-path instructions and free them
}

void RegisterAllocator::print_deadlock()
{
  fmt::print("Frontend Register Allocation Table        Backend Register Allocation Table\n");
  for (size_t i = 0; i < frontend_RAT.size(); ++i) {
    fmt::print("Arch reg: {:3}    Phys reg: {:3}            Arch reg: {:3}    Phys reg: {:3}\n", i, frontend_RAT[i], i, backend_RAT[i]);
  }

  if (count_free_registers() == 0) {
    fmt::print("\n**WARNING!! WARNING!!** THE PHYSICAL REGISTER FILE IS COMPLETELY OCCUPIED.\n");
    fmt::print("It is extremely likely your register file size is too small.\n");
  }

  fmt::print("\nPhysical Register File\n");
  for (size_t i = 0; i < physical_register_file.size(); ++i) {
    fmt::print("Phys reg: {:3}\t Arch reg: {:3}\t Producer: {}\t Valid: {}\t Busy: {}\n", static_cast<int>(i),
               static_cast<int>(physical_register_file.at(i).arch_reg_index), physical_register_file.at(i).producing_instruction_id,
               physical_register_file.at(i).valid, physical_register_file.at(i).busy);
  }
  fmt::print("\n");
}
